import json
import os
from typing import Dict, Optional, List

from pydantic import BaseModel, ConfigDict
from requests_oauthlib import OAuth2Session


# import logging
# import sys
# log = logging.getLogger('requests_oauthlib')
# log.addHandler(logging.StreamHandler(sys.stdout))
# log.setLevel(logging.DEBUG)


# DigiKey API implementation for Python, using Pydantic for deserialization
# examples from https://medium.com/@flaviohenriquepereiraoliveira/how-to-use-digikey-api-for-product-detail-c7d262cad14
# and https://requests-oauthlib.readthedocs.io/en/latest/oauth2_workflow.html


class DigiKeyApiConfig(BaseModel):
    client_id: str
    client_secret: str
    redirect_url: str = "https://localhost"


# Below are response formats as Pydantic models. Commented out fields are not implemented.
class Description(BaseModel):
    ProductDescription: str
    DetailedDescription: str


class Manufacturer(BaseModel):
    Id: int
    Name: str


class CategoryNode(BaseModel):
    CategoryId: int
    ParentId: int
    Name: str
    ProductCount: int
    NewProductCount: int
    ImageUrl: str
    SeoDescription: str
    # ChildCategories


class Product(BaseModel):
    model_config = ConfigDict(extra="allow")

    Description: Description
    Manufacturer: Manufacturer
    ManufacturerProductNumber: str
    UnitPrice: float  # in single quantity
    ProductUrl: Optional[str] = None
    DatasheetUrl: Optional[str] = None
    PhotoUrl: Optional[str] = None
    # ProductVariations
    QuantityAvailable: int
    # ProductStatus
    BackOrderNotAllowed: Optional[bool] = None
    NormallyStocking: Optional[bool] = None
    Discontinued: Optional[bool] = None
    EndOfLife: Optional[bool] = None
    Ncnr: Optional[bool] = None  # non-cancellable, non-returnable
    PrimaryVideoUrl: Optional[str] = None
    # Parameters
    # BaseProductNumber
    Category: CategoryNode
    # DateLastBuyChance
    ManufacturerLeadWeeks: str
    ManufacturerPublicQuantity: int
    # Series
    ShippingInfo: Optional[str] = None
    # Classifications


class ProductDetails(BaseModel):
    Product: Product


class ProductBarcodeResponse(BaseModel):
    """https://developer.digikey.com/products/barcode/barcoding/productbarcode"""
    DigiKeyPartNumber: str
    ManufacturerPartNumber: str
    ManufacturerName: str
    ProductDescription: str
    Quantity: int


class Product2dBarcodeResponse(BaseModel):
    """https://developer.digikey.com/products/barcode/barcoding/product2dbarcode"""
    DigiKeyPartNumber: str
    ManufacturerPartNumber: str
    ManufacturerName: str
    ProductDescription: str
    Quantity: int
    SalesorderId: int
    InvoiceId: int
    PurchaseOrder: str
    CountryOfOrigin: str
    LotCode: Optional[str] = None
    DateCode: Optional[str] = None


class DigiKeyApi():
    """DigiKey API implementation, initializing Oauth2 in the constructor.
    Optionally pass in a saved token to skip the Oauth2 flow."""
    kOauthCodePostfix = 'v1/oauth2/authorize'
    kOauthTokenPostfix = 'v1/oauth2/token'

    def __init__(self, api_config: DigiKeyApiConfig, token_filename: Optional[str] = None, sandbox: bool = False,
                 locale_language='en', locale_site='US'):
        self._locale_language = locale_language
        self._locale_site = locale_site

        if sandbox:
            self._api_prefix = "https://sandbox-api.digikey.com/"
        else:
            self._api_prefix = "https://api.digikey.com/"

        self._token_filename = token_filename
        if os.path.exists(self._token_filename):
            with open(self._token_filename) as f:
                token = json.load(f)
        else:
            token = None

        if token is None:
            self._oauth = OAuth2Session(api_config.client_id, redirect_uri=api_config.redirect_url,
                                        auto_refresh_url=self._api_prefix + self.kOauthTokenPostfix,
                                        auto_refresh_kwargs={'client_id': api_config.client_id,
                                                             'client_secret': api_config.client_secret},
                                        token_updater=self.token_saver)
            authorization_url, state = self._oauth.authorization_url(self._api_prefix + self.kOauthCodePostfix)
            response = input(f"Go to {authorization_url} in your browser and paste the returned URL, e.g. https://localhost/?code=...&...: ")
            token = self._oauth.fetch_token(self._api_prefix + self.kOauthTokenPostfix, authorization_response=response,
                                            include_client_id=True,  # otherwise Digikey rejects the request
                                            client_secret=api_config.client_secret)
            self.token_saver(token)
        else:
            self._oauth = OAuth2Session(api_config.client_id, redirect_uri=api_config.redirect_url,
                                        auto_refresh_url=self._api_prefix + self.kOauthTokenPostfix,
                                        auto_refresh_kwargs={'client_id': api_config.client_id,
                                                             'client_secret': api_config.client_secret},
                                        token=token, token_updater=self.token_saver)

    def token_saver(self, token: Dict[str, str]):
        with open(self._token_filename, 'w') as f:
            json.dump(token, f)

    def barcode2d(self, barcode: str) -> Product2dBarcodeResponse:
        """Product 2d barcode API, taking in the raw scanned barcode with original (un-escaped) special symbols."""
        response = self._oauth.get(self._api_prefix + f"Barcoding/v3/Product2DBarcodes/{barcode}",
                                   headers={'X-DIGIKEY-Client-Id': self._oauth.client_id})
        assert response.status_code == 200, f"error response {response}: {response.text}"
        return Product2dBarcodeResponse.model_validate_json(response.text)

    def barcode(self, barcode: str) -> ProductBarcodeResponse:
        """Product (1d / linear) barcode API, taking in the raw scanned barcode."""
        response = self._oauth.get(self._api_prefix + f'Barcoding/v3/ProductBarcodes/{barcode}',
                                   headers={'X-DIGIKEY-Client-Id': self._oauth.client_id})
        assert response.status_code == 200, f"error response {response}: {response.text}"
        return ProductBarcodeResponse.model_validate_json(response.text)

    def product_details(self, product_number: str) -> ProductDetails:
        """Product details API, taking in a manufacture or DigiKey part number."""
        response = self._oauth.get(self._api_prefix + f"products/v4/search/{product_number}/productdetails",
                                   headers={'X-DIGIKEY-Client-Id': self._oauth.client_id,
                                            'X-DIGIKEY-Locale-Language': self._locale_language,
                                            'X-DIGIKEY-Locale-Site': self._locale_site})
        assert response.status_code == 200, f"error response {response}: {response.text}"
        print(response.text)
        return ProductDetails.model_validate_json(response.text)
