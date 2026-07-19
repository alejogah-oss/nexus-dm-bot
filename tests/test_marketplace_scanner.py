import marketplace_poster

def test_scanner_car_fields_usa_datos_reales():
    car = {"make": "Honda", "model": "Civic", "yr": "2019",
           "mileage": 45000, "price": 16500, "color": "Blue",
           "title": "2019 Honda Civic EX", "description": "buen carro"}
    f = marketplace_poster.scanner_car_fields(car)
    assert f["make"] == "Honda"        # marca real, NO "Toyota"
    assert f["mileage"] == "45000"     # millaje real, NO "500"
    assert f["price"] == "16500"       # precio completo, NO enganche (20%)
    assert f["interior_color"] == "Black"
    assert f["exterior_color"] == "Blue"
    assert f["condition"] == "Excellent"
    assert f["title"] == "2019 Honda Civic EX"

def test_scanner_car_fields_make_fallback():
    # Si el scanner no trae marca, cae a Toyota (dealer Toyota) sin romper
    f = marketplace_poster.scanner_car_fields({"model": "Corolla", "yr": "2020",
                                               "mileage": 10, "price": 20000, "color": "White"})
    assert f["make"] == "Toyota" and f["exterior_color"] == "White"
