"""
Splunk Service for Query Execution and Result Processing.

This service provides integration with Splunk to execute SPL queries
and process results to determine appropriate visualization types.
Uses the official splunk-sdk library for reliable connection handling.
"""

from typing import Dict, Any, List, Optional
from app.core.config import settings
import json
import re
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

try:
    import splunklib.client as client
    import splunklib.results as results
    SPLUNK_SDK_AVAILABLE = True
except ImportError:
    SPLUNK_SDK_AVAILABLE = False
    print("⚠️ splunk-sdk not installed. Install with: pip install splunk-sdk")


class SplunkService:
    """
    Service for executing Splunk queries and processing results.
    
    Uses splunk-sdk for reliable connection and job management.
    Handles result analysis to determine the best visualization type.
    """
    
    def __init__(self):
        """
        Initialize Splunk service with connection configuration.
        
        Reads configuration from settings:
        - splunk_host: Splunk instance hostname or IP
        - splunk_port: Splunk management port (default: 8089)
        - splunk_username: Splunk username
        - splunk_password: Splunk password
        - splunk_verify_ssl: Whether to verify SSL certificates
        """
        if not SPLUNK_SDK_AVAILABLE:
            print("⚠️ splunk-sdk not available - Splunk integration disabled")
            self.service = None
            return
            
        self.host = settings.splunk_host
        self.port = settings.splunk_port
        self.username = settings.splunk_username
        self.password = settings.splunk_password
        self.verify_ssl = settings.splunk_verify_ssl
        self.service = None
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        if not self.host:
            print("⚠️ Splunk not configured - query execution will be disabled")
            return
        
        if not self.username or not self.password:
            print("⚠️ Splunk credentials not configured")
        else:
            print(f"✅ Splunk service will connect to {self.host}:{self.port}")
    
    def _connect(self) -> client.Service:
        """
        Create and return a Splunk service connection.
        
        Returns:
            client.Service: Connected Splunk service instance
            
        Raises:
            ValueError: If Splunk is not configured
            Exception: If connection fails
        """
        if not self.host or not self.username or not self.password:
            raise ValueError("Splunk is not configured. Please set SPLUNK_HOST, SPLUNK_USERNAME, and SPLUNK_PASSWORD.")
        
        if self.service is None:
            # Create service connection
            self.service = client.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                scheme="https" if self.verify_ssl else "http",
                verify=self.verify_ssl
            )
            print(f"✅ Connected to Splunk at {self.host}:{self.port}")
        
        return self.service
    
    async def execute_query(
        self,
        query: str,
        earliest_time: Optional[str] = None,
        latest_time: Optional[str] = None,
        output_mode: str = "json"
    ) -> Dict[str, Any]:
        """
        Execute a Splunk query and return results.
        
        Uses splunk-sdk to handle job creation, polling, and result retrieval.
        
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
                - job_id: Search job ID
        
        Raises:
            ValueError: If Splunk is not configured
            Exception: If query execution fails
        """
        if not SPLUNK_SDK_AVAILABLE:
            raise ValueError("splunk-sdk is not installed. Install with: pip install splunk-sdk")
        
        # Connect to Splunk
        service = self._connect()
        
        # Prepare search parameters
        # Note: Don't add "search" prefix if query already starts with it
        search_query = query if query.strip().startswith("search ") else f"search {query}"
        
        search_kwargs = {
            "search": search_query,
            "output_mode": output_mode,
            "count": 1000,  # Limit results
        }
        
        if earliest_time:
            search_kwargs["earliest_time"] = earliest_time
        if latest_time:
            search_kwargs["latest_time"] = latest_time
        
        # Execute search in thread pool (splunk-sdk is synchronous)
        loop = asyncio.get_event_loop()
        
        try:
            # Create search job and get results
            job_results = await loop.run_in_executor(
                self._executor,
                lambda: self._execute_search_sync(service, search_kwargs)
            )
            
            return job_results
            
        except Exception as e:
            print(f"❌ Error executing Splunk query: {e}")
            import traceback
            print(traceback.format_exc())
            raise
    
    def _execute_search_sync(
        self,
        service: client.Service,
        search_kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Synchronously execute search using splunk-sdk.
        
        This method runs in a thread pool to avoid blocking.
        
        Args:
            service: Connected Splunk service
            search_kwargs: Search parameters
            
        Returns:
            Dict[str, Any]: Query results
        """
        # Create search job
        job = service.jobs.create(**search_kwargs)
        job_id = job.sid
        print(f"📊 Created Splunk job: {job_id}")
        
        # Wait for job to complete
        while not job.is_done():
            job.refresh()
            # Check for errors
            if hasattr(job, 'content') and job.content.get('dispatchState') == 'FAILED':
                error_msg = job.content.get('messages', [{}])[0].get('text', 'Unknown error')
                raise ValueError(f"Splunk job failed: {error_msg}")
        
        print(f"✅ Splunk job {job_id} completed")
        
        # Get results
        result_stream = results.ResultsReader(
            job.results(
                output_mode=search_kwargs.get("output_mode", "json"),
                count=search_kwargs.get("count", 1000)
            )
        )
        
        # Parse results
        results_list = []
        fields = set()
        
        for result in result_stream:
            if isinstance(result, results.Message):
                # Handle messages (errors, warnings)
                if result.type == "ERROR":
                    raise ValueError(f"Splunk error: {result.message}")
                elif result.type == "WARN":
                    print(f"⚠️ Splunk warning: {result.message}")
                continue
            
            if isinstance(result, dict):
                results_list.append(result)
                fields.update(result.keys())
        
        # Get job properties
        job.refresh()
        is_done = job.is_done()
        
        return {
            "results": results_list,
            "fields": list(fields),
            "preview": not is_done,  # Preview if job is not fully done
            "job_id": job_id
        }
    
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
        return (
            SPLUNK_SDK_AVAILABLE and
            self.host is not None and
            self.username is not None and
            self.password is not None
        )


# Global instance
splunk_service = SplunkService()
