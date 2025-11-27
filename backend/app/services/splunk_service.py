"""
Splunk Service for Query Execution and Result Processing.

This service provides integration with Splunk to execute SPL queries
and process results to determine appropriate visualization types.
"""

from typing import Dict, Any, List, Optional
import requests
from requests.auth import HTTPBasicAuth
from app.core.config import settings
import json
import re
from datetime import datetime


class SplunkService:
    """
    Service for executing Splunk queries and processing results.
    
    Handles connection to Splunk, query execution, and result analysis
    to determine the best visualization type (chart, table, single-value, etc.).
    """
    
    def __init__(self):
        """
        Initialize Splunk service with connection configuration.
        
        Reads configuration from settings:
        - splunk_host: Splunk instance URL
        - splunk_port: Splunk management port (default: 8089)
        - splunk_username: Splunk username
        - splunk_password: Splunk password
        - splunk_verify_ssl: Whether to verify SSL certificates
        
        Raises:
            ValueError: If required configuration is missing
        """
        self.host = settings.splunk_host
        self.port = settings.splunk_port
        self.username = settings.splunk_username
        self.password = settings.splunk_password
        self.verify_ssl = settings.splunk_verify_ssl
        self.base_url = None
        
        if not self.host:
            print("⚠️ Splunk not configured - query execution will be disabled")
            return
        
        # Construct base URL
        scheme = "https" if self.verify_ssl else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}"
        
        if not self.username or not self.password:
            print("⚠️ Splunk credentials not configured")
        else:
            print(f"✅ Splunk service initialized for {self.base_url}")
    
    def _get_auth(self) -> Optional[HTTPBasicAuth]:
        """
        Get HTTP Basic Auth for Splunk requests.
        
        Returns:
            HTTPBasicAuth: Authentication object or None if credentials not set
        """
        if self.username and self.password:
            return HTTPBasicAuth(self.username, self.password)
        return None
    
    async def execute_query(
        self,
        query: str,
        earliest_time: Optional[str] = None,
        latest_time: Optional[str] = None,
        output_mode: str = "json"
    ) -> Dict[str, Any]:
        """
        Execute a Splunk query and return results.
        
        Args:
            query: SPL query string to execute
            earliest_time: Earliest time for search (e.g., "-1h@h", "-24h@h")
            latest_time: Latest time for search (default: "now")
            output_mode: Output format (json, csv, xml) - default: json
        
        Returns:
            Dict[str, Any]: Query results with:
                - results: List of result rows
                - fields: List of field names
                - preview: Whether results are preview
                - job_id: Search job ID (for async queries)
        
        Raises:
            ValueError: If Splunk is not configured
            requests.RequestException: If query execution fails
        """
        if not self.base_url or not self.username or not self.password:
            raise ValueError("Splunk is not configured. Please set SPLUNK_HOST, SPLUNK_USERNAME, and SPLUNK_PASSWORD.")
        
        # Prepare search parameters
        search_params = {
            "search": f"search {query}",
            "output_mode": output_mode,
            "count": 1000,  # Limit results
        }
        
        if earliest_time:
            search_params["earliest_time"] = earliest_time
        if latest_time:
            search_params["latest_time"] = latest_time
        
        # Execute search job
        search_url = f"{self.base_url}/services/search/jobs"
        auth = self._get_auth()
        
        try:
            # Create search job (run in thread pool to avoid blocking)
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    search_url,
                    data=search_params,
                    auth=auth,
                    verify=self.verify_ssl,
                    timeout=30
                )
            )
            response.raise_for_status()
            
            # Parse job ID from response
            job_data = response.text
            job_id_match = re.search(r'<sid>([^<]+)</sid>', job_data)
            if not job_id_match:
                raise ValueError("Failed to get job ID from Splunk response")
            
            job_id = job_id_match.group(1)
            
            # Wait for job to complete and get results
            results = await self._wait_for_job_completion(job_id)
            
            return results
            
        except requests.RequestException as e:
            print(f"❌ Error executing Splunk query: {e}")
            raise
    
    async def _wait_for_job_completion(
        self,
        job_id: str,
        max_wait: int = 60,
        poll_interval: float = 0.5
    ) -> Dict[str, Any]:
        """
        Wait for Splunk search job to complete and retrieve results.
        
        Args:
            job_id: Splunk search job ID
            max_wait: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
        
        Returns:
            Dict[str, Any]: Job results with fields and data
        
        Raises:
            TimeoutError: If job doesn't complete within max_wait time
        """
        import asyncio
        import time
        
        status_url = f"{self.base_url}/services/search/jobs/{job_id}"
        results_url = f"{self.base_url}/services/search/jobs/{job_id}/results"
        auth = self._get_auth()
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # Check job status (run in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            status_response = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    status_url,
                    params={"output_mode": "json"},
                    auth=auth,
                    verify=self.verify_ssl,
                    timeout=10
                )
            )
            status_response.raise_for_status()
            status_data = status_response.json()
            
            # Check if job is done
            dispatch_state = status_data.get("entry", [{}])[0].get("content", {}).get("dispatchState", "")
            
            if dispatch_state == "DONE":
                # Get results (run in thread pool)
                results_response = await loop.run_in_executor(
                    None,
                    lambda: requests.get(
                        results_url,
                        params={"output_mode": "json", "count": 1000},
                        auth=auth,
                        verify=self.verify_ssl,
                        timeout=10
                    )
                )
                results_response.raise_for_status()
                results_data = results_response.json()
                
                return {
                    "results": results_data.get("results", []),
                    "fields": [f.get("name") for f in results_data.get("fields", [])],
                    "preview": results_data.get("preview", False),
                    "job_id": job_id
                }
            elif dispatch_state in ["FAILED", "FINALIZING"]:
                raise ValueError(f"Splunk job failed with state: {dispatch_state}")
            
            # Wait before next check
            await asyncio.sleep(poll_interval)
        
        raise TimeoutError(f"Splunk job {job_id} did not complete within {max_wait} seconds")
    
    def analyze_result_type(
        self,
        results: List[Dict[str, Any]],
        fields: List[str],
        query: str
    ) -> Dict[str, Any]:
        """
        Analyze Splunk query results to determine visualization type.
        
        Examines the query and results to determine the best visualization:
        - timechart -> chart (time series)
        - stats count (single value) -> single-value
        - stats count by -> chart (bar/pie)
        - stats with time field -> chart (time series)
        - Regular search -> table
        
        Args:
            results: List of result rows
            fields: List of field names
            query: Original SPL query
        
        Returns:
            Dict[str, Any]: Visualization configuration with:
                - visualizationType: 'table' | 'chart' | 'single-value' | 'gauge'
                - visualizationConfig: Chart configuration
                - chartData: Formatted data for charts
                - isTimeSeries: Whether data is time series
        """
        query_lower = query.lower()
        num_results = len(results)
        num_fields = len(fields)
        
        # Check for timechart command
        if "timechart" in query_lower:
            return self._create_timechart_config(results, fields)
        
        # Check for single value (stats count/sum/avg without by)
        if re.search(r'stats\s+(count|sum|avg|max|min)', query_lower) and "by" not in query_lower:
            if num_results == 1 and num_fields <= 2:
                return self._create_single_value_config(results, fields)
        
        # Check for stats with grouping (chart)
        if "stats" in query_lower and "by" in query_lower:
            return self._create_chart_config(results, fields, query_lower)
        
        # Check for time field in results (time series)
        time_fields = ["_time", "time", "timestamp", "date"]
        has_time_field = any(field.lower() in time_fields for field in fields)
        
        if has_time_field and num_results > 1:
            return self._create_timechart_config(results, fields)
        
        # Default to table
        return {
            "visualizationType": "table",
            "visualizationConfig": None,
            "chartData": None,
            "isTimeSeries": False
        }
    
    def _create_timechart_config(
        self,
        results: List[Dict[str, Any]],
        fields: List[str]
    ) -> Dict[str, Any]:
        """Create configuration for time series chart."""
        time_fields = ["_time", "time", "timestamp", "date"]
        time_field = next((f for f in fields if f.lower() in time_fields), None)
        value_fields = [f for f in fields if f.lower() not in time_fields]
        
        chart_data = []
        for row in results:
            data_point: Dict[str, Any] = {}
            if time_field:
                time_value = row.get(time_field, "")
                # Format time value
                data_point["time"] = str(time_value)
            
            for field in value_fields:
                data_point[field] = row.get(field, 0)
            
            chart_data.append(data_point)
        
        return {
            "visualizationType": "chart",
            "visualizationConfig": {
                "chartType": "line",
                "xAxis": time_field or "time",
                "yAxis": value_fields[0] if value_fields else "value",
                "series": value_fields
            },
            "chartData": chart_data,
            "isTimeSeries": True,
            "allowChartTypeSwitch": True
        }
    
    def _create_single_value_config(
        self,
        results: List[Dict[str, Any]],
        fields: List[str]
    ) -> Dict[str, Any]:
        """Create configuration for single value display."""
        if not results:
            return {"visualizationType": "table"}
        
        first_row = results[0]
        value_field = fields[0] if fields else "value"
        value = first_row.get(value_field, 0)
        
        # Try to convert to number
        try:
            numeric_value = float(value) if value else 0
        except (ValueError, TypeError):
            numeric_value = 0
        
        return {
            "visualizationType": "single-value",
            "visualizationConfig": {
                "format": "number",
                "valueField": value_field,
                "unit": ""
            },
            "singleValue": numeric_value,
            "chartData": None,
            "isTimeSeries": False
        }
    
    def _create_chart_config(
        self,
        results: List[Dict[str, Any]],
        fields: List[str],
        query: str
    ) -> Dict[str, Any]:
        """Create configuration for bar/pie chart."""
        # Determine chart type based on number of categories
        num_categories = len(results)
        
        # Use pie chart for small number of categories, bar for more
        chart_type = "pie" if num_categories <= 5 else "bar"
        
        # First field is usually the category, second is the value
        category_field = fields[0] if len(fields) > 0 else "category"
        value_field = fields[1] if len(fields) > 1 else "value"
        
        chart_data = []
        for row in results:
            chart_data.append({
                "name": str(row.get(category_field, "")),
                "value": float(row.get(value_field, 0)) if row.get(value_field) else 0
            })
        
        return {
            "visualizationType": "chart",
            "visualizationConfig": {
                "chartType": chart_type,
                "xAxis": category_field,
                "yAxis": value_field,
                "labelField": category_field,
                "valueField": value_field
            },
            "chartData": chart_data,
            "isTimeSeries": False,
            "allowChartTypeSwitch": True
        }
    
    def format_query_result(
        self,
        splunk_result: Dict[str, Any],
        query: str
    ) -> Dict[str, Any]:
        """
        Format Splunk query result for frontend consumption.
        
        Converts Splunk results into the format expected by QueryBlock component.
        
        Args:
            splunk_result: Raw Splunk query result
            query: Original query string
        
        Returns:
            Dict[str, Any]: Formatted result with:
                - columns: List of column names
                - rows: List of row data
                - rowCount: Number of rows
                - visualizationType: Recommended visualization
                - visualizationConfig: Chart configuration
                - chartData: Formatted chart data
        """
        results = splunk_result.get("results", [])
        fields = splunk_result.get("fields", [])
        
        if not results:
            return {
                "columns": fields,
                "rows": [],
                "rowCount": 0,
                "visualizationType": "table"
            }
        
        # Convert results to rows
        rows = []
        for result in results:
            row = [result.get(field, "") for field in fields]
            rows.append(row)
        
        # Analyze visualization type
        viz_config = self.analyze_result_type(results, fields, query)
        
        return {
            "columns": fields,
            "rows": rows,
            "rowCount": len(rows),
            "executionTime": None,  # Could be added from Splunk job stats
            "visualizationType": viz_config.get("visualizationType", "table"),
            "visualizationConfig": viz_config.get("visualizationConfig"),
            "singleValue": viz_config.get("singleValue"),
            "gaugeValue": viz_config.get("gaugeValue"),
            "chartData": viz_config.get("chartData"),
            "isTimeSeries": viz_config.get("isTimeSeries", False),
            "allowChartTypeSwitch": viz_config.get("allowChartTypeSwitch", False)
        }
    
    def is_available(self) -> bool:
        """
        Check if Splunk service is available and configured.
        
        Returns:
            bool: True if Splunk is configured and ready to use
        """
        return self.base_url is not None and self.username is not None and self.password is not None


# Global instance
splunk_service = SplunkService()

