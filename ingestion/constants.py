GRID_EMISSION_FACTORS = {
    'Maharashtra': 0.82,
    'Delhi': 0.87,
    'Tamil Nadu': 0.78,
    'Gujarat': 0.88,
    'Telangana': 0.85,
    'default': 0.82,
}

TRAVEL_EMISSION_FACTORS = {
    'FLIGHT_ECONOMY_DOMESTIC': 0.133,
    'FLIGHT_ECONOMY_INTERNATIONAL': 0.195,
    'FLIGHT_BUSINESS_MULTIPLIER': 2.9,
    'TRAIN_AC': 0.041,
    'CAR': 0.171,
    'HOTEL_PER_NIGHT': 31.2,
}

AIRPORT_COORDINATES = {
    'BOM': {'lat': 19.0896, 'lon': 72.8656, 'country': 'IN', 'city': 'Mumbai'},
    'DEL': {'lat': 28.5562, 'lon': 77.1000, 'country': 'IN', 'city': 'Delhi'},
    'BLR': {'lat': 13.1986, 'lon': 77.7066, 'country': 'IN', 'city': 'Bengaluru'},
    'MAA': {'lat': 12.9941, 'lon': 80.1709, 'country': 'IN', 'city': 'Chennai'},
    'COK': {'lat': 10.1520, 'lon': 76.4019, 'country': 'IN', 'city': 'Kochi'},
    'HYD': {'lat': 17.2313, 'lon': 78.4300, 'country': 'IN', 'city': 'Hyderabad'},
    'CCU': {'lat': 22.6520, 'lon': 88.4463, 'country': 'IN', 'city': 'Kolkata'},
    'AMD': {'lat': 23.0772, 'lon': 72.6347, 'country': 'IN', 'city': 'Ahmedabad'},
    'LHR': {'lat': 51.4700, 'lon': -0.4543, 'country': 'GB', 'city': 'London'},
    'DXB': {'lat': 25.2532, 'lon': 55.3657, 'country': 'AE', 'city': 'Dubai'},
    'SFO': {'lat': 37.6213, 'lon': -122.3790, 'country': 'US', 'city': 'San Francisco'},
}

INDIAN_AIRPORT_CODES = [
    'BOM', 'DEL', 'BLR', 'MAA', 'COK', 'HYD', 'CCU', 'AMD', 'PNQ', 'GOI', 'JAI', 'LKO'
]

UNIT_CONVERSION = {
    'L': 1.0,
    'LTR': 1.0,
    'LITRE': 1.0,
    'LITRES': 1.0,
    'GAL': 3.785,
    'GALLON': 3.785,
    'KG': None,
}
