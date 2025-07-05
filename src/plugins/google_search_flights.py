import os
from typing import Annotated
from semantic_kernel.functions import kernel_function
from serpapi import GoogleSearch

class FlightSearch:
  @kernel_function(
      description="Searches for flights based on departure, destination, and date.",
      name="search_flights",
  )
  def search_flights(
      self,
      departure: Annotated[str, "The departure airport or city."],
      destination: Annotated[str, "The destination airport or city."],
      date: Annotated[str, "The date of travel (YYYY-MM-DD)."]
  ) -> Annotated[str, "A JSON string containing flight information."]:
    """
    Searches for flights using the SerpApi Google Flights API.
    """
    params = {
        "engine": "google_flights",
        "departure_id": departure,
        "arrival_id": destination,
        "outbound_date": date,
        "api_key": os.environ.get("SERPAPI_API_KEY") # Make sure to set SERPAPI_API_KEY in your environment variables
    }

    search = GoogleSearch(params)
    results = search.get_dict()

    # You can process the results further if needed
    return str(results)
    
params = {
  "engine": "google_flights",
  "hl": "en",
  "gl": "ro",
  "departure_id": "CDG",
  "arrival_id": "AUS",
  "outbound_date": "2025-07-05",
  "return_date": "2025-07-11",
  "currency": "CAD",
  "type": "1",
  "api_key": "secret_api_key"
}

search = GoogleSearch(params)
results = search.get_dict()