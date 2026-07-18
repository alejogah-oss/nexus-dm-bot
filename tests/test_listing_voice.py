from listing_voice import LISTING_SYSTEM, build_listing_prompt

CAR = {"yr": "2021", "make": "Toyota", "model": "Corolla", "trim": "SE",
       "engine": "2.0L 4cyl", "fuel": "Gasoline", "body": "Sedan", "drive": "FWD",
       "mileage": 42000, "price": 17500, "notes": "un solo dueño"}

def test_system_rules():
    for must in ["JSON", "100", "(954) 910-6671", "English", "Español"]:
        assert must in LISTING_SYSTEM

def test_prompt_contains_car_data():
    p = build_listing_prompt(CAR)
    for must in ["2021", "Corolla", "SE", "42,000", "$17,500", "un solo dueño"]:
        assert must in p
