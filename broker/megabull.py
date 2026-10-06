"""
MegaBull Paper Trading API Wrapper
Provides clean Python methods to interact with the MegaBull REST API.
"""

import os
from typing import Any, Dict, List, Optional, Union
import requests
from dotenv import load_dotenv


class MegaBullAPIError(Exception):
    """Custom exception raised when an API request to MegaBull fails."""

    def __init__(self, status_code: int, message: str, response_data: Any = None):
        super().__init__(f"MegaBull API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.response_data = response_data


class MegaBull:
    """
    Client for interacting with the MegaBull Paper Trading REST API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.megabull.in",
    ):
        # Load environment variables if present
        load_dotenv()

        # Retrieve API key
        resolved_key = api_key or os.getenv("MEGABULL_API_KEY")
        if not resolved_key:
            raise ValueError(
                "MegaBull API key not found. Please set MEGABULL_API_KEY in your .env file "
                "or pass it directly to MegaBull(api_key=...)."
            )

        self.base_url = base_url.rstrip("/")
        self._api_key = resolved_key

        # Configure session with standard headers
        self.session = requests.Session()
        self.session.headers.update({
            "api-key": self._api_key,
            "Content-Type": "application/json"
        })

    def __repr__(self) -> str:
        # Safe string representation that never exposes the API key
        return f"<MegaBull base_url='{self.base_url}'>"

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Union[Dict[str, Any], List[Any]]] = None,
        timeout: int = 15,
    ) -> Any:
        """
        Internal helper to send HTTP requests to MegaBull API.

        Args:
            method: HTTP method (e.g. "GET", "POST", "PUT", "DELETE").
            endpoint: API endpoint path (e.g. "/api/user/my").
            params: Optional query parameters dictionary.
            json_data: Optional JSON body payload (dict or list).
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON response from the server.

        Raises:
            MegaBullAPIError: If the server returns an HTTP error status code.
            requests.RequestException: For network/connection failures.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to connect to MegaBull API: {e}") from e

        # Handle successful response
        if 200 <= response.status_code < 300:
            if response.text.strip():
                try:
                    return response.json()
                except ValueError:
                    return response.text
            return {}

        # Handle error response cleanly
        error_message = response.text
        response_json = None
        try:
            response_json = response.json()
            if isinstance(response_json, dict):
                # MegaBull error responses often contain 'message' or 'error' keys
                error_message = response_json.get("message") or response_json.get("error") or str(response_json)
        except ValueError:
            pass

        raise MegaBullAPIError(
            status_code=response.status_code,
            message=str(error_message),
            response_data=response_json,
        )

    # -------------------------------------------------------------------------
    # Account & Profile
    # -------------------------------------------------------------------------

    def get_user_profile(self) -> Dict[str, Any]:
        """
        Fetch user profile details including virtual money balance.
        Endpoint: GET /api/user/my
        """
        return self._request("GET", "/api/user/my")

    # -------------------------------------------------------------------------
    # Market Watch & Instruments
    # -------------------------------------------------------------------------

    def get_marketwatch(self, as_dataframe: bool = False) -> Any:
        """
        Fetch the user's market watch list.
        Endpoint: GET /api/marketwatch/my

        Args:
            as_dataframe: If True, returns a pandas DataFrame instead of a list of dicts.
        """
        data = self._request("GET", "/api/marketwatch/my")
        if as_dataframe:
            import pandas as pd
            return pd.DataFrame(data)
        return data

    def get_instruments(self, as_dataframe: bool = False) -> Any:
        """
        Fetch all tradable instruments master list.
        Endpoint: GET /api/marketwatch/instruments

        Args:
            as_dataframe: If True, downloads and parses the instruments CSV into a pandas DataFrame.
        """
        data = self._request("GET", "/api/marketwatch/instruments")
        if as_dataframe:
            import io
            import pandas as pd
            download_url = data.get("downloadUrl") if isinstance(data, dict) else None
            if not download_url:
                raise MegaBullAPIError(500, "Download URL missing from instruments response", data)
            csv_response = requests.get(download_url, timeout=30)
            csv_response.raise_for_status()
            return pd.read_csv(io.StringIO(csv_response.text))
        return data

    def get_marketwatch_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve quote and instrument information for a given symbol from the user's marketwatch.

        Args:
            symbol: Trading symbol name (e.g. 'RELIANCE', 'INFY', 'NIFTY 50').

        Returns:
            Dictionary with instrument info and lastPrice, or None if not present in marketwatch.
        """
        items = self.get_marketwatch(as_dataframe=False)
        symbol_upper = symbol.strip().upper()
        for item in items:
            if item.get("tradingSymbol", "").upper() == symbol_upper:
                return item
        return None

    # -------------------------------------------------------------------------
    # Orders
    # -------------------------------------------------------------------------

    def get_orders(self) -> Any:
        """
        Fetch open and executed orders.
        Endpoint: GET /api/order/my
        """
        return self._request("GET", "/api/order/my")

    def place_order(self, order_data: Dict[str, Any]) -> Any:
        """
        Place a buy or sell order.
        Endpoint: POST /api/order/buysell
        """
        return self._request("POST", "/api/order/buysell", json_data=order_data)

    def modify_order(self, order_id: Union[str, int], order_data: Dict[str, Any]) -> Any:
        """
        Modify a pending order.
        Endpoint: PUT /api/order/buysell/{orderId}
        """
        return self._request("PUT", f"/api/order/buysell/{order_id}", json_data=order_data)

    def cancel_orders(self, order_ids: List[Union[str, int]]) -> Any:
        """
        Bulk cancel orders by ID.
        Endpoint: PUT /api/order/bulk/cancel
        """
        return self._request("PUT", "/api/order/bulk/cancel", json_data=order_ids)

    # -------------------------------------------------------------------------
    # Portfolio (Positions & Holdings)
    # -------------------------------------------------------------------------

    def get_positions(self) -> Any:
        """
        Fetch open positions.
        Endpoint: GET /api/position/my
        """
        return self._request("GET", "/api/position/my")

    def get_holdings(self) -> Any:
        """
        Fetch delivery holdings.
        Endpoint: GET /api/holding/my
        """
        return self._request("GET", "/api/holding/my")

    # -------------------------------------------------------------------------
    # Reports
    # -------------------------------------------------------------------------

    def get_virtual_money_report(self, start_date: str, end_date: str) -> Any:
        """
        Fetch virtual money report for a date range.
        Endpoint: GET /api/report/virtual/{start}/{end}
        """
        return self._request("GET", f"/api/report/virtual/{start_date}/{end_date}")

    def get_monthly_report(self, month: Union[int, str], year: Union[int, str]) -> Any:
        """
        Fetch monthly trading P&L report.
        Endpoint: GET /api/report/monthly/{month}/{year}
        """
        return self._request("GET", f"/api/report/monthly/{month}/{year}")

    def get_daily_report(self, date_str: str) -> Any:
        """
        Fetch day-wise positions report.
        Endpoint: GET /api/report/monthly/day/{date_str}
        """
        return self._request("GET", f"/api/report/monthly/day/{date_str}")
