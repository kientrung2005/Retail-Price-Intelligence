import re

BRAND_KEYWORDS = {
    "apple": "Apple",
    "iphone": "Apple",
    "macbook": "Apple",
    "ipad": "Apple",
    "samsung": "Samsung",
    "xiaomi": "Xiaomi",
    "redmi": "Xiaomi",
    "poco": "Xiaomi",
    "oppo": "OPPO",
    "vivo": "Vivo",
    "realme": "Realme",
    "nokia": "Nokia",
    "tecno": "Tecno",
    "asus": "ASUS",
    "nubia": "Nubia",
    "honor": "Honor",
    "itel": "Itel",
    "nothing": "Nothing",
    "masstel": "Masstel",
    "vsmart": "Vsmart",
    "motorola": "Motorola",
    "mobell": "Mobell",
    "lenovo": "Lenovo",
    "msi": "MSI",
    "acer": "Acer",
    "hp": "HP",
    "dell": "Dell",
    "lg": "LG",
    "gigabyte": "Gigabyte",
    "huawei": "Huawei",
    "garmin": "Garmin",
    "amazfit": "Amazfit",
    "kieslect": "Kieslect",
    "coros": "Coros",
    "soundpeats": "Soundpeats",
    "black shark": "Black Shark",
    "myalo": "MyAlo",
    "mibro": "Mibro",
    "viettel": "Viettel",
    "kospet": "Kospet",
    "imoo": "Imoo",
    "goly": "Goly",
    "kavvo": "Kavvo",
    "riversong": "Riversong",
    "wonlex": "Wonlex",
    "aula": "AULA",
    "akko": "AKKO",
    "logitech": "Logitech",
    "dareu": "Dareu",
    "rapoo": "Rapoo",
    "corsair": "Corsair",
    "jbl": "JBL",
    "sony": "Sony",
    "harman": "Harman Kardon",
    "marshall": "Marshall",
    "bose": "Bose",
    "anker": "Anker",
    "baseus": "Baseus",
    "energizer": "Energizer",
    "havit": "Havit",
    "edifier": "Edifier",
    "tineco": "Tineco",
    "roborock": "Roborock",
    "dreame": "Dreame",
    "ecovacs": "Ecovacs",
    "ezviz": "Ezviz",
    "imou": "Imou",
    "tapo": "TP-Link",
    "tp-link": "TP-Link",
    "tplink": "TP-Link",
    "totolink": "Totolink",
    "tcl": "TCL",
    "coocaa": "Coocaa",
    "casper": "Casper",
    "toshiba": "Toshiba",
    "sharp": "Sharp",
    "panasonic": "Panasonic",
    "philips": "Philips",
    "tefal": "Tefal",
    "sunhouse": "Sunhouse",
    "kangaroo": "Kangaroo",
    "karofi": "Karofi",
    "levoit": "Levoit",
    "coway": "Coway",
    "dyson": "Dyson",
    "cuckoo": "Cuckoo",
    "midea": "Midea",
    "electrolux": "Electrolux"
}

def normalize_brand(name: str, fallback_brand: str = "") -> str:
    if not name:
        return "Other"
        
    name_lower = name.lower()
    
    if fallback_brand:
        fb_lower = fallback_brand.strip().lower()
        if fb_lower in BRAND_KEYWORDS:
            return BRAND_KEYWORDS[fb_lower]
        for key, val in BRAND_KEYWORDS.items():
            if re.search(rf'\b{re.escape(key)}\b', fb_lower):
                return val
        return fallback_brand.strip().capitalize()
        
    for key, val in BRAND_KEYWORDS.items():
        if re.search(rf'\b{re.escape(key)}\b', name_lower):
            return val
            
    return "Other"
