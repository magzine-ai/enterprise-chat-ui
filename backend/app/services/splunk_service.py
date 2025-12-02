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

# Timezone handling
try:
    from zoneinfo import ZoneInfo
    HAS_ZONEINFO = True
except ImportError:
    # Fallback for Python < 3.9
    try:
        from backports.zoneinfo import ZoneInfo
        HAS_ZONEINFO = True
    except ImportError:
        HAS_ZONEINFO = False
        ZoneInfo = None
        import time

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
        output_mode: str = "json",
        user_timezone: Optional[str] = None
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
            search_kwargs: Search parameters (must include 'search' key)
            
        Returns:
            Dict[str, Any]: Query results
        """
        # Extract search query (required as positional argument)
        search_query = search_kwargs.get("search")
        if not search_query:
            raise ValueError("Search query is required")
        
        # Create a copy of kwargs without 'search' for keyword arguments
        job_kwargs = {k: v for k, v in search_kwargs.items() if k != "search"}
        
        # Create search job - query is positional, other params are keyword args
        job = service.jobs.create(search_query, **job_kwargs)
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
        result_count = 0
        
        print(f"📊 Processing results from Splunk job {job_id}...")
        
        for result in result_stream:
            if isinstance(result, results.Message):
                # Handle messages (errors, warnings)
                print(f"📨 Splunk message [{result.type}]: {result.message}")
                if result.type == "ERROR":
                    raise ValueError(f"Splunk error: {result.message}")
                elif result.type == "WARN":
                    print(f"⚠️ Splunk warning: {result.message}")
                continue
            
            if isinstance(result, dict):
                result_count += 1
                results_list.append(result)
                fields.update(result.keys())
                
                # Log first few results for debugging
                if result_count <= 3:
                    print(f"📋 Result {result_count}: {json.dumps(result, indent=2, default=str)}")
        
        print(f"✅ Processed {result_count} results with {len(fields)} unique fields")
        print(f"📊 Fields: {', '.join(sorted(fields))}")
        
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
        query: str,
        user_timezone: Optional[str] = None
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
            return self._create_timechart_config(results, fields, user_timezone)
        
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
            return self._create_timechart_config(results, fields, user_timezone)
        
        # Default to table
        return {
            "visualizationType": "table",
            "visualizationConfig": None,
            "chartData": None,
            "isTimeSeries": False
        }
    
    def _format_time_for_chart(self, time_value: Any, user_timezone: Optional[str] = None) -> str:
        """
        Format time value to local 12-hour format with AM/PM for chart display.
        
        Handles multiple input formats:
        - Unix epoch timestamp (float/int) - most common from Splunk JSON
        - ISO 8601 string
        - Already formatted string (HH:MM or similar)
        
        Args:
            time_value: Time value from Splunk (epoch, ISO, or string)
            user_timezone: User's timezone (e.g., "America/New_York", "UTC")
        
        Returns:
            str: Formatted time as "H:MM AM/PM" in user's timezone (e.g., "4:45 PM", "10:30 AM")
        """
        if not time_value:
            return ""
        
        # Determine timezone
        if user_timezone and HAS_ZONEINFO:
            try:
                tz = ZoneInfo(user_timezone)
            except Exception:
                tz = ZoneInfo("UTC") if HAS_ZONEINFO else None
        else:
            tz = ZoneInfo("UTC") if HAS_ZONEINFO else None
        
        # Try to parse as epoch timestamp (most common from Splunk JSON)
        try:
            if isinstance(time_value, (int, float)):
                # Splunk returns epoch in seconds
                if HAS_ZONEINFO:
                    dt = datetime.fromtimestamp(float(time_value), tz=ZoneInfo("UTC"))
                    # Convert to user's timezone
                    if tz:
                        local_dt = dt.astimezone(tz)
                    else:
                        local_dt = dt
                else:
                    # Fallback: use UTC without timezone conversion
                    dt = datetime.utcfromtimestamp(float(time_value))
                    local_dt = dt
                # Format as 12-hour with AM/PM (e.g., "4:45 PM")
                hour_12 = local_dt.hour % 12
                if hour_12 == 0:
                    hour_12 = 12
                period = "AM" if local_dt.hour < 12 else "PM"
                return f"{hour_12}:{local_dt.minute:02d} {period}"
        except (ValueError, TypeError, OSError) as e:
            pass
        
        # Try to parse as ISO 8601 string
        try:
            if isinstance(time_value, str):
                # Try various ISO formats
                iso_formats = [
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%f%z"
                ]
                
                for fmt in iso_formats:
                    try:
                        dt = datetime.strptime(time_value, fmt)
                        # If no timezone info, assume UTC
                        if 'Z' in fmt or ('+' not in time_value and '-' not in time_value[-6:]):
                            if HAS_ZONEINFO:
                                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                        # Convert to user timezone
                        if HAS_ZONEINFO and tz and dt.tzinfo:
                            local_dt = dt.astimezone(tz)
                        else:
                            local_dt = dt
                        # Format as 12-hour with AM/PM (e.g., "4:45 PM")
                        hour_12 = local_dt.hour % 12
                        if hour_12 == 0:
                            hour_12 = 12
                        period = "AM" if local_dt.hour < 12 else "PM"
                        return f"{hour_12}:{local_dt.minute:02d} {period}"
                    except ValueError:
                        continue
                
                # Check if already in HH:MM or H:MM format
                if re.match(r'^\d{1,2}:\d{2}', time_value):
                    # Try to parse and reformat to 12-hour with AM/PM
                    try:
                        # Parse as 24-hour time
                        time_part = time_value[:5]
                        hour, minute = map(int, time_part.split(':'))
                        # Convert to 12-hour format
                        period = "AM" if hour < 12 else "PM"
                        hour_12 = hour if hour <= 12 else hour - 12
                        if hour_12 == 0:
                            hour_12 = 12
                        return f"{hour_12}:{minute:02d} {period}"
                    except Exception:
                        return time_value[:5]  # Return original if parsing fails
        except Exception:
            pass
        
        # Fallback: return as string
        return str(time_value)
    
    def _create_timechart_config(
        self,
        results: List[Dict[str, Any]],
        fields: List[str],
        user_timezone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create configuration for time series chart with formatted time values."""
        time_fields = ["_time", "time", "timestamp", "date"]
        # Filter out Splunk internal fields that shouldn't be displayed
        internal_fields = ["_span", "_raw", "_time", "_indextime"]
        time_field = next((f for f in fields if f.lower() in time_fields), None)
        # Exclude time fields and internal Splunk fields from value fields
        value_fields = [f for f in fields if f.lower() not in time_fields and f.lower() not in internal_fields]
        
        chart_data = []
        for row in results:
            data_point: Dict[str, Any] = {}
            if time_field:
                time_value = row.get(time_field, "")
                # Format time value as local HH:MM
                formatted_time = self._format_time_for_chart(time_value, user_timezone)
                data_point["time"] = formatted_time
                # Keep original time for reference/sorting if needed
                data_point["_original_time"] = time_value
            else:
                # If no time field found, create a placeholder
                data_point["time"] = ""
            
            for field in value_fields:
                data_point[field] = row.get(field, 0)
            
            chart_data.append(data_point)
        
        # Sort by original time to ensure chronological order
        if time_field:
            try:
                chart_data.sort(key=lambda x: x.get("_original_time", 0) if isinstance(x.get("_original_time"), (int, float)) else 0)
            except Exception:
                pass  # If sorting fails, keep original order
        
        return {
            "visualizationType": "chart",
            "visualizationConfig": {
                "chartType": "line",
                "xAxis": "time",  # Always use "time" field (formatted), not original field name
                "yAxis": value_fields[0] if value_fields else "value",
                "series": value_fields,
                "timeFormat": "HH:MM"  # Indicate format to frontend
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
        query: str,
        user_timezone: Optional[str] = None
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
        viz_config = self.analyze_result_type(results, fields, query, user_timezone)
        
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
