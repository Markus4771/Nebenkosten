from app.calculation import calc_share

def test_area(): assert calc_share(1200,'area',80,400)==240.0
def test_percent(): assert calc_share(1000,'percent',15,0)==150.0
def test_direct(): assert calc_share(999,'direct',0,0,123.45)==123.45
def test_zero_total(): assert calc_share(999,'area',50,0)==0.0
