import re
from typing import Dict, Any, Optional, List

# Standardized Mapping of 34 Provinces & Cities (Post-Merger Model)
# Grouped by 3 Macro Regions: Miền Bắc, Miền Trung, Miền Nam

LOCATIONS_34 = {
    # === 11 ĐƠN VỊ GIỮ NGUYÊN KHÔNG SÁP NHẬP ===
    "HN": {
        "code": "HN",
        "name": "Thành phố Hà Nội",
        "short_name": "Hà Nội",
        "region": "Miền Bắc",
        "type": "Thành phố trực thuộc Trung ương",
        "merged_from": ["Hà Nội"],
        "cps_ids": ["24"]
    },
    "HUE": {
        "code": "HUE",
        "name": "Thành phố Huế",
        "short_name": "Huế",
        "region": "Miền Trung",
        "type": "Thành phố trực thuộc Trung ương",
        "merged_from": ["Thừa Thiên Huế", "Thừa Thiên - Huế", "Huế"],
        "cps_ids": ["57"]
    },
    "CB": {
        "code": "CB",
        "name": "Tỉnh Cao Bằng",
        "short_name": "Cao Bằng",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Cao Bằng"],
        "cps_ids": []
    },
    "DB": {
        "code": "DB",
        "name": "Tỉnh Điện Biên",
        "short_name": "Điện Biên",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Điện Biên"],
        "cps_ids": []
    },
    "HT": {
        "code": "HT",
        "name": "Tỉnh Hà Tĩnh",
        "short_name": "Hà Tĩnh",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Hà Tĩnh"],
        "cps_ids": ["25"]
    },
    "LC": {
        "code": "LC",
        "name": "Tỉnh Lai Châu",
        "short_name": "Lai Châu",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Lai Châu"],
        "cps_ids": []
    },
    "LS": {
        "code": "LS",
        "name": "Tỉnh Lạng Sơn",
        "short_name": "Lạng Sơn",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Lạng Sơn"],
        "cps_ids": ["36"]
    },
    "NA": {
        "code": "NA",
        "name": "Tỉnh Nghệ An",
        "short_name": "Nghệ An",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Nghệ An"],
        "cps_ids": ["41"]
    },
    "QN": {
        "code": "QN",
        "name": "Tỉnh Quảng Ninh",
        "short_name": "Quảng Ninh",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Quảng Ninh"],
        "cps_ids": ["49"]
    },
    "SL": {
        "code": "SL",
        "name": "Tỉnh Sơn La",
        "short_name": "Sơn La",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Sơn La"],
        "cps_ids": []
    },
    "TH": {
        "code": "TH",
        "name": "Tỉnh Thanh Hóa",
        "short_name": "Thanh Hóa",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Thanh Hóa"],
        "cps_ids": ["56"]
    },

    # === 23 ĐƠN VỊ HÌNH THÀNH SAU SẮP XẾP ===
    "TQ": {
        "code": "TQ",
        "name": "Tỉnh Tuyên Quang",
        "short_name": "Tuyên Quang",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Hà Giang", "Tuyên Quang"],
        "cps_ids": []
    },
    "LCA": {
        "code": "LCA",
        "name": "Tỉnh Lào Cai",
        "short_name": "Lào Cai",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Lào Cai", "Yên Bái"],
        "cps_ids": []
    },
    "TN": {
        "code": "TN",
        "name": "Tỉnh Thái Nguyên",
        "short_name": "Thái Nguyên",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Bắc Kạn", "Thái Nguyên"],
        "cps_ids": ["55"]
    },
    "PT": {
        "code": "PT",
        "name": "Tỉnh Phú Thọ",
        "short_name": "Phú Thọ",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Vĩnh Phúc", "Phú Thọ", "Hòa Bình"],
        "cps_ids": ["44", "62", "29"]
    },
    "BN": {
        "code": "BN",
        "name": "Tỉnh Bắc Ninh",
        "short_name": "Bắc Ninh",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Bắc Ninh", "Bắc Giang"],
        "cps_ids": ["6", "5"]
    },
    "HY": {
        "code": "HY",
        "name": "Tỉnh Hưng Yên",
        "short_name": "Hưng Yên",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Hưng Yên", "Thái Bình"],
        "cps_ids": ["31", "54"]
    },
    "HP": {
        "code": "HP",
        "name": "Thành phố Hải Phòng",
        "short_name": "Hải Phòng",
        "region": "Miền Bắc",
        "type": "Thành phố trực thuộc Trung ương",
        "merged_from": ["Hải Dương", "Hải Phòng"],
        "cps_ids": ["26", "27"]
    },
    "NB": {
        "code": "NB",
        "name": "Tỉnh Ninh Bình",
        "short_name": "Ninh Bình",
        "region": "Miền Bắc",
        "type": "Tỉnh",
        "merged_from": ["Hà Nam", "Ninh Bình", "Nam Định"],
        "cps_ids": ["23", "42", "40"]
    },
    "QT": {
        "code": "QT",
        "name": "Tỉnh Quảng Trị",
        "short_name": "Quảng Trị",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Quảng Bình", "Quảng Trị"],
        "cps_ids": ["46", "50"]
    },
    "DN": {
        "code": "DN",
        "name": "Thành phố Đà Nẵng",
        "short_name": "Đà Nẵng",
        "region": "Miền Trung",
        "type": "Thành phố trực thuộc Trung ương",
        "merged_from": ["Quảng Nam", "Đà Nẵng"],
        "cps_ids": ["15"]
    },
    "QNG": {
        "code": "QNG",
        "name": "Tỉnh Quảng Ngãi",
        "short_name": "Quảng Ngãi",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Kon Tum", "Quảng Ngãi"],
        "cps_ids": ["48"]
    },
    "GL": {
        "code": "GL",
        "name": "Tỉnh Gia Lai",
        "short_name": "Gia Lai",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Gia Lai", "Bình Định"],
        "cps_ids": ["21", "9"]
    },
    "KH": {
        "code": "KH",
        "name": "Tỉnh Khánh Hòa",
        "short_name": "Khánh Hòa",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Ninh Thuận", "Khánh Hòa"],
        "cps_ids": ["43", "32"]
    },
    "LD": {
        "code": "LD",
        "name": "Tỉnh Lâm Đồng",
        "short_name": "Lâm Đồng",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Lâm Đồng", "Đắk Nông", "Bình Thuận"],
        "cps_ids": ["38", "11"]
    },
    "DL": {
        "code": "DL",
        "name": "Tỉnh Đắk Lắk",
        "short_name": "Đắk Lắk",
        "region": "Miền Trung",
        "type": "Tỉnh",
        "merged_from": ["Đắk Lắk", "Phú Yên"],
        "cps_ids": ["16", "45"]
    },
    "HCM": {
        "code": "HCM",
        "name": "Thành phố Hồ Chí Minh",
        "short_name": "Hồ Chí Minh",
        "region": "Miền Nam",
        "type": "Thành phố trực thuộc Trung ương",
        "merged_from": ["Bà Rịa - Vũng Tàu", "Bình Dương", "TP. Hồ Chí Minh", "Hồ Chí Minh", "Sài Gòn", "TP.HCM"],
        "cps_ids": ["2", "8", "30"]
    },
    "DNA": {
        "code": "DNA",
        "name": "Thành phố Đồng Nai",
        "short_name": "Đồng Nai",
        "region": "Miền Nam",
        "type": "Thành phố trực thuộc Trung ương",
        "merged_from": ["Đồng Nai", "Bình Phước"],
        "cps_ids": ["19", "10"]
    },
    "TN_S": {
        "code": "TN_S",
        "name": "Tỉnh Tây Ninh",
        "short_name": "Tây Ninh",
        "region": "Miền Nam",
        "type": "Tỉnh",
        "merged_from": ["Tây Ninh", "Long An"],
        "cps_ids": ["53", "39"]
    },
    "CT": {
        "code": "CT",
        "name": "Thành phố Cần Thơ",
        "short_name": "Cần Thơ",
        "region": "Miền Nam",
        "type": "Thành phố trực thuộc Trung ương",
        "merged_from": ["Cần Thơ", "Sóc Trăng", "Hậu Giang"],
        "cps_ids": ["14", "51", "28"]
    },
    "VL": {
        "code": "VL",
        "name": "Tỉnh Vĩnh Long",
        "short_name": "Vĩnh Long",
        "region": "Miền Nam",
        "type": "Tỉnh",
        "merged_from": ["Bến Tre", "Vĩnh Long", "Trà Vinh"],
        "cps_ids": ["7", "61", "59"]
    },
    "DT": {
        "code": "DT",
        "name": "Tỉnh Đồng Tháp",
        "short_name": "Đồng Tháp",
        "region": "Miền Nam",
        "type": "Tỉnh",
        "merged_from": ["Tiền Giang", "Đồng Tháp"],
        "cps_ids": ["58", "20"]
    },
    "CM": {
        "code": "CM",
        "name": "Tỉnh Cà Mau",
        "short_name": "Cà Mau",
        "region": "Miền Nam",
        "type": "Tỉnh",
        "merged_from": ["Bạc Liêu", "Cà Mau"],
        "cps_ids": ["3", "12"]
    },
    "AG": {
        "code": "AG",
        "name": "Tỉnh An Giang",
        "short_name": "An Giang",
        "region": "Miền Nam",
        "type": "Tỉnh",
        "merged_from": ["An Giang", "Kiên Giang"],
        "cps_ids": ["1", "33"]
    }
}

# Reverse lookup table: maps any old/current province name to its new 34-Province entity
_LOOKUP_MAP: Dict[str, Dict[str, Any]] = {}

for code, loc in LOCATIONS_34.items():
    # Register full name and short name
    _LOOKUP_MAP[loc["name"].lower()] = loc
    _LOOKUP_MAP[loc["short_name"].lower()] = loc
    for old_p in loc["merged_from"]:
        _LOOKUP_MAP[old_p.lower()] = loc

def map_location_to_34(location_str: str) -> Dict[str, Any]:
    """
    Map any store province/city string (including pre-merger 63 provinces)
    to the standardized 34-Province post-merger entity.
    """
    if not location_str:
        return LOCATIONS_34["HN"] # Default fallback

    clean_str = location_str.strip().lower()
    clean_str = re.sub(r'^(tỉnh|thành phố|tp\.?)\s*', '', clean_str).strip()

    # Direct match
    if clean_str in _LOOKUP_MAP:
        return _LOOKUP_MAP[clean_str]

    # Partial / substring match
    for key, loc in _LOOKUP_MAP.items():
        clean_key = re.sub(r'^(tỉnh|thành phố|tp\.?)\s*', '', key).strip()
        if clean_key and (clean_key in clean_str or clean_str in clean_key):
            return loc

    return LOCATIONS_34["HN"]


def get_all_34_locations() -> List[Dict[str, Any]]:
    """Return all 34 post-merger provinces and cities."""
    return list(LOCATIONS_34.values())
