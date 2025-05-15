import ee
from flask import Flask, request, jsonify
import requests
from datetime import datetime


ee.Authenticate()
ee.Initialize(project="ndviproject-459415")
app = Flask(__name__)


def validate_request(request):
    """
    Validate the request parameters for coordinates and date.
    :param request: Flask request object
    :return: List of errors (if any)
    """
    errors = []

    try:

        coordinates = request.json.get("coordinates")
        date = request.json.get("date")

        if not isinstance(coordinates, list) or len(coordinates) < 4:
            errors.append("Coordinates must be a list with at least 4 points.")

        else:
            for i, point in enumerate(coordinates):
                if not (isinstance(point, list) and len(point) == 2):
                    errors.append(f"Point {i+1} is not a list of two elements.")
                    continue
                lon, lat = point
                if not (isinstance(lon, float) and isinstance(lat, float)):
                    errors.append(f"Point {i+1} must contain two floats (lon, lat).")

        try:
            datetime.strptime(date, "%Y-%m-%d")
        except (ValueError, TypeError):
            errors.append("Date must be a valid string in 'YYYY-MM-DD' format.")
    except Exception as e:
            errors.append(f"validate_request: {str(e)}")

    return errors



def get_open_meteo_weather(lat, lon, date):
    """
    Get daily weather data from Open-Meteo API for a given lat/lon and date.
    :param lat: Latitude (float)
    :param lon: Longitude (float)
    :param date: Date string in format 'YYYY-MM-DD'
    :return: Dictionary with weather parameters
    """
    # Define the URL with the parameters for the Open-Meteo API
    response_ = {"data": {}, "errors": []}

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"hourly=temperature_2m,relativehumidity_2m,wind_speed_10m,et0_fao_evapotranspiration&"
            f"start={date}T00:00:00Z&end={date}T23:59:59Z"
        )

        # Send the request to the API
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception("Failed to fetch data:", response.text)

        # Parse the JSON response
        data = response.json()

        # Extract the relevant hourly data
        hourly_data = data["hourly"]
        
        # Get the first 24 hours of data (since it's hourly data, it should be 24 hours)
        temperature = hourly_data["temperature_2m"][:24]
        humidity = hourly_data["relativehumidity_2m"][:24]
        wind_speed = hourly_data["wind_speed_10m"][:24]
        et0 = hourly_data.get("et0_fao_evapotranspiration", [0]*24)[:24]  # Assuming 0 if data is missing
        
        # Calculate the mean of temperature, humidity, and wind speed
        mean_temp = sum(temperature) / len(temperature)
        mean_humidity = sum(humidity) / len(humidity)
        mean_wind_speed = sum(wind_speed) / len(wind_speed)
        
        # Calculate the sum of ET0
        sum_et0 = sum(et0)
        
        # Return the computed statistics
        weather_data = {
            "mean_temperature_2m_C": mean_temp,
            "mean_humidity_2m_%": mean_humidity,
            "mean_wind_speed_10m_m_s": mean_wind_speed,
            "sum_et0_mm": sum_et0
        }
    
        response_["data"] = weather_data

    except Exception as e:
        response_["errors"].append(f"get_open_meteo_weather: {str(e)}")

    return response_



def get_ndvi_data(coordinates, date):
    """
    Get mean NDVI value from Google Earth Engine for a given polygon and date.
    :param coordinates: List of polygon coordinates [[[lon, lat], ...]]
    :param date: Date string in format 'YYYY-MM-DD'
    :return: Dictionary with NDVI mean value
    """
    response = {"data": {}, "errors": []}

    try:
        # Initialize EE if not already done
        if not ee.data._initialized:
            ee.Initialize()

        # Define the date range for the NDVI data
        start_date = ee.Date(date).advance(-1, 'day')
        end_date = ee.Date(date).advance(1, 'day')

        # Create a polygon geometry
        polygon = ee.Geometry.Polygon(coordinates)

        # Load Sentinel-2 image
        image = ee.ImageCollection('COPERNICUS/S2') \
            .filterBounds(polygon) \
            .filterDate(start_date, end_date) \
            .sort('CLOUDY_PIXEL_PERCENTAGE') \
            .first()

        # Compute NDVI
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI').clip(polygon)

        # Reduce region to compute mean NDVI
        mean_ndvi = ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=polygon,
            scale=10,
            maxPixels=1e9
        ).get('NDVI')

        ndvi_mean_value = mean_ndvi.getInfo()  # This is a float

        response["data"]["ndvi_mean"] = ndvi_mean_value
        print("NDVI mean value:", ndvi_mean_value)

    except Exception as e:
        response["errors"].append(f"get_ndvi_data: {str(e)}")

    return response



@app.route('/get_data', methods=['GET'])
def get_data():
    response = {
        "status": "success",
        "data": {}
    }
    try:

        errors = validate_request(request)
        if errors:
            return jsonify({"errors": errors}), 400
        
        # Get the parameters from the query string
        json_ = request.get_json()
        coordinates = json_['coordinates']
        date = json_['date']
        
        # Call the function to get weather data
        weather_data = get_open_meteo_weather(coordinates[0][0], coordinates[0][1], date)
        if weather_data["errors"]:
            return jsonify({"errors": weather_data["errors"]}), 400
        
        response["data"].update(weather_data["data"])

        # --------------------------------------------------------------------------------------


        # print(weather_data)
        # Call the function to get NDVI data
        ndvi_data = get_ndvi_data(coordinates, date)
        if ndvi_data["errors"]:
            return jsonify({"errors": ndvi_data["errors"]}), 400
        print(ndvi_data)
        response["data"].update(ndvi_data["data"])
        print(response)
        # Return the weather data as a JSON response
        return jsonify(response), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400














if __name__ == '__main__':
    app.run(debug=True)

