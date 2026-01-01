
try:
    from sgp4.api import jday, gstime
    print("Found jday and gstime in sgp4.api")
except ImportError:
    print("gstime or jday not in sgp4.api")
    try:
        from sgp4.conveniences import jday
        print("Found jday in sgp4.conveniences")
    except ImportError:
        print("jday not in sgp4.conveniences")

    try:
        from sgp4.propagation import gstime
        print("Found gstime in sgp4.propagation")
    except ImportError:
        print("gstime not in sgp4.propagation")
