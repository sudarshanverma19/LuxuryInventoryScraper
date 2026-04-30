"""
Shopify Admin GraphQL API client.

Handles staged file uploads, product creation, and variant management
via the Shopify Admin GraphQL API with built-in rate limiting and retries.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

import httpx

from config import SHOPIFY_STORE_URL, SHOPIFY_ACCESS_TOKEN, SHOPIFY_API_VERSION
from shopify_sync.retry import async_retry

logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class StagedUploadTarget:
    """Result from stagedUploadsCreate mutation."""
    url: str
    resource_url: str
    parameters: list[dict]  # [{"name": str, "value": str}, ...]


@dataclass
class ShopifyProductResult:
    """Result from productCreate mutation."""
    product_id: str  # Shopify GID
    title: str
    errors: list[dict] = field(default_factory=list)


@dataclass
class VariantInput:
    """Input for creating a product variant."""
    sku: Optional[str] = None
    price: Optional[float] = None
    option_values: list[str] = field(default_factory=list)  # e.g. ["Red", "XL"]
    inventory_quantity: Optional[int] = None


# ── GraphQL Mutations ─────────────────────────────────────────────────────

STAGED_UPLOADS_CREATE = """
mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets {
      url
      resourceUrl
      parameters {
        name
        value
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""

PRODUCT_CREATE = """
mutation productCreate($input: ProductInput!, $media: [CreateMediaInput!]) {
  productCreate(input: $input, media: $media) {
    product {
      id
      title
      handle
      status
      media(first: 20) {
        nodes {
          alt
          mediaContentType
          status
          ... on MediaImage {
            id
            image {
              url
            }
          }
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""

PRODUCT_VARIANTS_BULK_CREATE = """
mutation productVariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkCreate(productId: $productId, variants: $variants) {
    productVariants {
      id
      title
      sku
      price
    }
    userErrors {
      field
      message
    }
  }
}
"""


# ── Shopify Client ────────────────────────────────────────────────────────

class ShopifyClient:
    """
    Async Shopify Admin GraphQL API client.

    Usage:
        async with ShopifyClient() as client:
            target = await client.staged_upload("image.jpg", "image/jpeg", 12345)
            await client.upload_file(target, image_bytes)
            result = await client.create_product(...)
    """

    def __init__(
        self,
        store_url: Optional[str] = None,
        access_token: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self.store_url = (store_url or SHOPIFY_STORE_URL).rstrip("/")
        self.access_token = access_token or SHOPIFY_ACCESS_TOKEN
        self.api_version = api_version or SHOPIFY_API_VERSION
        self._client: Optional[httpx.AsyncClient] = None

        if not self.store_url or not self.access_token:
            raise ValueError(
                "Shopify credentials not configured. "
                "Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN in .env"
            )

    @property
    def graphql_url(self) -> str:
        return f"{self.store_url}/admin/api/{self.api_version}/graphql.json"

    @property
    def headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── GraphQL Execution ─────────────────────────────────────────────────

    async def _execute_graphql(
        self,
        query: str,
        variables: Optional[dict] = None,
    ) -> dict:
        """Execute a GraphQL mutation/query and return the response data."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with ShopifyClient()' context manager.")

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await self._client.post(
            self.graphql_url,
            json=payload,
            headers=self.headers,
        )

        # Handle HTTP-level rate limiting
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "2.0"))
            raise httpx.HTTPStatusError(
                f"Rate limited (429), retry after {retry_after}s",
                request=response.request,
                response=response,
            )

        response.raise_for_status()
        result = response.json()

        # Check for GraphQL-level errors
        if "errors" in result:
            error_messages = "; ".join(e.get("message", str(e)) for e in result["errors"])
            raise Exception(f"GraphQL errors: {error_messages}")

        # Log throttle status if available
        extensions = result.get("extensions", {})
        cost = extensions.get("cost", {})
        if cost:
            throttle = cost.get("throttleStatus", {})
            available = throttle.get("currentlyAvailable", "?")
            max_available = throttle.get("maximumAvailable", "?")
            logger.debug(f"[ShopifySync] API cost: {cost.get('requestedQueryCost', '?')}, "
                        f"available: {available}/{max_available}")

        return result.get("data", {})

    # ── Staged Uploads ────────────────────────────────────────────────────

    async def staged_upload(
        self,
        filename: str,
        content_type: str,
        file_size: int,
    ) -> StagedUploadTarget:
        """
        Create a staged upload target for a file.

        Args:
            filename: Name of the file
            content_type: MIME type (e.g. "image/jpeg")
            file_size: File size in bytes

        Returns:
            StagedUploadTarget with upload URL and parameters
        """
        # Determine resource type from content type
        resource = "IMAGE"
        if "video" in content_type:
            resource = "VIDEO"

        # Determine HTTP method based on upload URL type
        # Shopify uses FILE for direct PUT uploads or MULTIPART_FORM_DATA
        variables = {
            "input": [
                {
                    "resource": resource,
                    "filename": filename,
                    "mimeType": content_type,
                    "fileSize": str(file_size),
                    "httpMethod": "POST",
                }
            ]
        }

        async def _do_staged_upload():
            data = await self._execute_graphql(STAGED_UPLOADS_CREATE, variables)
            result = data.get("stagedUploadsCreate", {})

            user_errors = result.get("userErrors", [])
            if user_errors:
                error_msg = "; ".join(e.get("message", str(e)) for e in user_errors)
                raise Exception(f"Staged upload failed: {error_msg}")

            targets = result.get("stagedTargets", [])
            if not targets:
                raise Exception("No staged upload targets returned")

            target = targets[0]
            return StagedUploadTarget(
                url=target["url"],
                resource_url=target["resourceUrl"],
                parameters=target["parameters"],
            )

        return await async_retry(
            _do_staged_upload,
            max_retries=2,
            base_delay=2.0,
            description=f"staged upload for {filename}",
        )

    async def upload_file(
        self,
        target: StagedUploadTarget,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload a file to a staged upload target.

        Uses multipart form upload with the parameters from stagedUploadsCreate.

        Args:
            target: StagedUploadTarget from staged_upload()
            file_data: Raw file bytes
            filename: Original filename
            content_type: MIME type

        Returns:
            The resource URL for use in product creation
        """
        async def _do_upload():
            # Build multipart form data with parameters first, then the file
            form_data = {}
            for param in target.parameters:
                form_data[param["name"]] = param["value"]

            files = {
                "file": (filename, file_data, content_type),
            }

            # Use a fresh client for the upload (different host than GraphQL)
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=15.0),
                follow_redirects=True,
            ) as upload_client:
                response = await upload_client.post(
                    target.url,
                    data=form_data,
                    files=files,
                )

                # Staged uploads return various success codes (200, 201, 204)
                if response.status_code not in (200, 201, 204):
                    raise Exception(
                        f"File upload failed with status {response.status_code}: "
                        f"{response.text[:500]}"
                    )

            logger.debug(
                f"[ShopifySync] Uploaded {filename} ({len(file_data) / 1024:.0f}KB) → "
                f"{target.resource_url}"
            )
            return target.resource_url

        return await async_retry(
            _do_upload,
            max_retries=2,
            base_delay=3.0,
            description=f"file upload {filename}",
        )

    # ── Product Creation ──────────────────────────────────────────────────

    async def create_product(
        self,
        title: str,
        description_html: Optional[str] = None,
        vendor: Optional[str] = None,
        product_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        media_sources: Optional[list[str]] = None,
        status: str = "DRAFT",
    ) -> ShopifyProductResult:
        """
        Create a product on Shopify with optional media.

        Args:
            title: Product title
            description_html: HTML description
            vendor: Brand/vendor name
            product_type: Product type/category
            tags: List of tags
            media_sources: List of resource URLs from staged uploads

        Returns:
            ShopifyProductResult with product ID and any errors
        """
        product_input = {
            "title": title,
            "status": status.upper(),
        }
        if description_html:
            product_input["descriptionHtml"] = description_html
        if vendor:
            product_input["vendor"] = vendor
        if product_type:
            product_input["productType"] = product_type
        if tags:
            product_input["tags"] = tags

        variables = {"input": product_input}

        # Attach media if we have staged upload URLs
        if media_sources:
            variables["media"] = [
                {
                    "originalSource": source_url,
                    "alt": title,
                    "mediaContentType": "IMAGE",
                }
                for source_url in media_sources
            ]

        async def _do_create():
            data = await self._execute_graphql(PRODUCT_CREATE, variables)
            result = data.get("productCreate", {})

            user_errors = result.get("userErrors", [])
            if user_errors:
                error_msg = "; ".join(
                    f"{e.get('field', 'unknown')}: {e.get('message', str(e))}"
                    for e in user_errors
                )
                raise Exception(f"Product creation failed: {error_msg}")

            product = result.get("product", {})
            if not product or not product.get("id"):
                raise Exception("Product creation returned no product ID")

            return ShopifyProductResult(
                product_id=product["id"],
                title=product.get("title", title),
            )

        return await async_retry(
            _do_create,
            max_retries=2,
            base_delay=2.0,
            description=f"product create '{title[:50]}'",
        )

    # ── Variant Creation ──────────────────────────────────────────────────

    async def create_variants(
        self,
        product_id: str,
        variants: list[VariantInput],
    ) -> list[dict]:
        """
        Bulk create variants for a product.

        Args:
            product_id: Shopify product GID
            variants: List of VariantInput objects

        Returns:
            List of created variant dicts with id, title, sku, price
        """
        if not variants:
            return []

        variant_inputs = []
        for v in variants:
            vi = {}
            if v.sku:
                vi["sku"] = v.sku
            if v.price is not None:
                vi["price"] = str(v.price)
            if v.option_values:
                vi["optionValues"] = [
                    {"optionName": "Size" if i == 0 else "Color", "name": val}
                    for i, val in enumerate(v.option_values)
                ]
            variant_inputs.append(vi)

        variables = {
            "productId": product_id,
            "variants": variant_inputs,
        }

        async def _do_create_variants():
            data = await self._execute_graphql(PRODUCT_VARIANTS_BULK_CREATE, variables)
            result = data.get("productVariantsBulkCreate", {})

            user_errors = result.get("userErrors", [])
            if user_errors:
                error_msg = "; ".join(e.get("message", str(e)) for e in user_errors)
                logger.warning(f"[ShopifySync] Variant creation had errors: {error_msg}")

            return result.get("productVariants", [])

        return await async_retry(
            _do_create_variants,
            max_retries=2,
            base_delay=2.0,
            description=f"variants for {product_id}",
        )

    # ── Utility ───────────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """Check if Shopify credentials are configured."""
        return bool(self.store_url and self.access_token)
