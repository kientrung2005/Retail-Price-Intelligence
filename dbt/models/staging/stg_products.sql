{{ config(
    materialized='table',
    pre_hook="""
        CREATE OR REPLACE FUNCTION title_case_preserve(str text) RETURNS text AS $fn$
        DECLARE
            word text;
            res text[] := '{}';
        BEGIN
            IF str IS NULL THEN RETURN NULL; END IF;
            FOREACH word IN ARRAY string_to_array(str, ' ') LOOP
                IF length(word) > 0 THEN
                    res := array_append(res, upper(left(word, 1)) || substr(word, 2));
                ELSE
                    res := array_append(res, word);
                END IF;
            END LOOP;
            RETURN array_to_string(res, ' ');
        END;
        $fn$ LANGUAGE plpgsql IMMUTABLE;

        CREATE OR REPLACE FUNCTION strip_trailing_colors(str text) RETURNS text AS $fn$
        DECLARE
            s text := str;
            prev text;
            color_reg text := '[-–/,\s]*(xanh\s*đậm\s*đen|đen\s*xanh\s*đậm|xanh\s*đậm|xám\s*trắng|trắng\s*xám|đen\s*đỏ|đỏ\s*đen|đen\s*trắng|trắng\s*đen|đen\s*xám|xám\s*đen|đen\s*cam|cam\s*đen|đen\s*hồng|hồng\s*đen|xanh\s*lá\s*đen|xanh\s*dương\s*trắng|xanh\s*trắng|trắng\s*xanh|cyan\s*blue|yellow\s*blue|pink\s*white|white\s*black|black\s*white|white\s*pink|pink\s*black|black\s*pink|rose\s*gold|rosegold|goku\s*cream|midnight(\s*r[0-9]+)?|neon|glacier|grey|gray|black|white|blue|green|red|purple|yellow|pink|orange|brown|silver|gold|đen|trắng|xanh|đỏ|tím|vàng|hồng|xám|cam|nâu|be|ghi|bạc|kim|bk)\s*$';
            dangle_reg text := '\s*[-–/,\s&+\*]+$';
        BEGIN
            IF s IS NULL THEN RETURN NULL; END IF;
            FOR i IN 1..3 LOOP
                prev := s;
                s := REGEXP_REPLACE(s, color_reg, '', 'i');
                s := REGEXP_REPLACE(s, dangle_reg, '', 'g');
                IF s = prev THEN EXIT; END IF;
            END LOOP;
            RETURN TRIM(REGEXP_REPLACE(s, '\s+', ' ', 'g'));
        END;
        $fn$ LANGUAGE plpgsql IMMUTABLE;
    """
) }}

WITH distinct_products AS MATERIALIZED (
    SELECT DISTINCT
        product_name,
        category
    FROM {{ source('raw', 'raw_products') }}
    WHERE product_name IS NOT NULL
),

cleaned_catalog_base AS MATERIALIZED (
    SELECT
        product_name,
        category,
                TRIM(REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(
                                    REGEXP_REPLACE(
                                        REGEXP_REPLACE(
                                            REGEXP_REPLACE(
                                                REGEXP_REPLACE(
                                                    REGEXP_REPLACE(
                                                        REGEXP_REPLACE(
                                                            LOWER(TRIM(product_name)),
                                                            '([0-9]+)\.000', '\1000', 'g'
                                                            ),
                                                            '\s*\|.*$|\s+[iI]\s+chính hãng.*$', '', 'g'
                                                        ),
                                                        '[-–\s]*(công\s*thái\s*học|ergonomic|ergo)\M', '', 'g'
                                                    ),
                                                    '/(?:ch|ap)-[0-9a-z\-]+', '', 'g'
                                                ),
                                                '\m(?:ch|ap)-[0-9a-z\-]+', '', 'g'
                                            ),
                                            '\m(scimitar\s+elite\s+se)\M.*$', '\1', 'g'
                                        ),
                                        '\m(loa thanh soundbar|loa soundbar|bộ loa thanh|bộ loa vi tính|loa vi tính|bộ loa|dàn loa|dàn âm thanh|loa thanh|loa kéo|loa karaoke xách tay|loa karaoke|loa bluetooth|soundbar)\M', 'loa', 'g'
                                    ),
                                    '\m(bộ\s*bàn\s*phím\s*(?:và\s*)?(?:[\+\&]\s*)?chuột|combo\s*bàn\s*phím\s*(?:và\s*)?(?:[\+\&]\s*)?chuột|bàn\s*phím\s*(?:và\s*)?(?:[\+\&]\s*)?chuột|bộ\s*bàn\s*phím|combo\s*bàn\s*phím)\M', 'bộ bàn phím', 'g'
                                ),
                                '\m(bao da\s*bàn phím|bàn phím\s*[\+\&]\s*bao da|bao da\s*kèm\s*bàn phím|bàn phím\s*kiêm\s*bao da|bao da\s*kèm|kèm\s*bao da|bao da)\M', 'bàn phím', 'g'
                            ),
                            '^(bàn phím)\s+(ipad\s+(?:air|pro|\d+)?\s*\d*)\s+(logitech\s+combo\s+touch|logitech\s+slim\s+folio|zagg\s+pro\s+key\s*2|zagg\s+messenger\s+folio\s*2|esr\s+rebound\s+magnetic\s*360)(.*)$',
                            '\1 \3 \2 \4', 'g'
                        ),
                        '\m(chính hãng apple việt nam|chính hãng việt nam|chính hãng vn/a|nhập khẩu chính hãng|hàng chính hãng|chính hãng|vn/a|công ty|nhập khẩu|đã kích hoạt|đổi bảo hành|likenew|new 100%|bảo hành [0-9]+ (tháng|năm)|sim viettel)\M|\m(eumẫu mới|đenmẫu mới|mẫu mới)\M|\m(chủ động khử tiếng ồn|chống ồn chủ động|khử tiếng ồn|chống ồn|true wireless|tws|choàng đầu|chụp tai|nhét tai|in-ear|on-ear|over-ear|bluetooth)\M|\m(full\s*hd|full|fhd|uhd|qhd|ips|va|tn|s30gd|s3)\M|\m(kèm|tích hợp)\s+(cáp|dây)\s*(rút gọn|dây rút|đôi)?\s*(lightning|type[-\s]*c|usb[-\s]*c|micro)?(\s*và\s*|\s*[-–]\s*)?(cáp\s*)?(lightning|type[-\s]*c|usb[-\s]*c|micro)?(\s*[-–]\s*)?(lightning|type[-\s]*c|usb[-\s]*c|micro)?\M|\m(có màn hình|màn hình lcd|màn hình led|màn hình hiển thị|màn hình|hỗ trợ sạc laptop|1c1a|2c1a|2a1c|1c|2c|1a|2a|pd\s*qc\s*[\d\.]*|pd\s*[\d\.]*w?|qc\s*[\d\.]*)\M|\m(cơ không dây|cơ có dây|không dây|có dây|limitless riding combo|creator edition|standard edition|advanced tracking combo|adventure combo|fly more combo|creator combo|premium combo|ultra combo|advanced combo|standard combo|combo phụ kiện|power combo|battery combo|all in one|combo(?!\s*(touch|[0-9]+))|standard|advanced|kèm thẻ nhớ.*|thế hệ [0-9]+|gen [0-9]+|đèn thông minh|bộ combo)\M|\m(crystal uhd|mini led|neo qled|qled|oled|amoled|hd|4k|8k|5 7k|7k|5mp|4mp|3mp|2mp|[0-9]+hz|[0-9]+(\.[0-9]+)?\s*(inch|in|\")|năm [0-9]{4}|2026|2025|2024|2023|2022|2021)\M|\m(core ultra [0-9][-\s]\w+|core i[0-9][-\s]\w+|core [0-9] [0-9]+|ryzen [0-9][-\s]\w+|apple m[0-9] \w+|(i3|i5|i7|i9)[-\s]\w+)\M|\m(kèm (bút|cáp sạc|củ sạc|tai nghe|2 mic|2 micro|micro|cáp lightning.*)|kèm 2 micro|có\s*mic|kèm\s*mic)\M|\m(gps \+ cellular|cellular|gps|wifi|5g|4g|lte)\M|\m(viền titanium|viền titan|viền gốm|viền thép|viền nhôm|viền kim loại|dây thể thao|dây cao su|dây silicone|dây silicon|dây da phối|dây da|dây milanese|dây milan|dây woven|dây composite|dây nylon|dây gốm|dây thép|size s/m & m/l|size s/m|size m/l|cỡ s/m|cỡ m/l|s/m|m/l|titanium|composite|leather|silicone|silicon|milanese|woven|nylon)\M|\m(blue switch|red switch|brown switch|black switch|linear switch|tactile switch|clicky switch|switch|red backlight|blue backlight|white backlight|rgb backlight|backlight|rgb led|rgb|black & pink|black on white|matcha red bean|ocean star|ice crystal|ice green|ice blue|sea blue|glacier blue|comic|contour|graffiti|gradient)\M|\m(titan tự nhiên|titan sa mạc|titan đen|titan trắng|xám bạc|vàng đồng|xanh lá|xanh dương|xanh rêu|xanh gốm|xanh navy|ánh sao|đen đỏ|đen trắng|xám trắng|trắng tím đậm|tím nhạt be|đen xám vàng|đen xanh lá cam|đen hồng|đen|trắng|xanh|đỏ|tím|vàng|hồng|xám|cam|nâu|be|ghi|bạc|kim|titan|black|white|blue|green|red|purple|yellow|pink|orange|brown|gray|grey|silver|golden|gold|midnight|starlight|space gray|ice|graphite|pink\s*white|white\s*black|black\s*white|quartz|jelly\s*pink|sakura\s*pink|vàng\s*hồng|xám\s*đen|xanh\s*lá\s*đen|xanh\s*bóng\s*đêm|cyan\s*blue|yellow\s*blue|xanh\s*dương\s*trắng)\M|\m(1vh[a-z0-9]+|x161[a-z0-9]+|cmh[a-z0-9]+|cth[a-z0-9]+|cvh[a-z0-9]+|cwh[a-z0-9]+|5th[a-z0-9]+|eg61h|ga65h|ga6h|ga6|32gb|1tb|propanel)\M|\m(osmo)\M|\m(qd\s*mini\s*led|miniled|qd|micro\s*led)\M|\m([a-z0-9]+)?(eexxv|pxexxv|gaexxv|xxv)\M|\m(eu|global|quốc tế|bản quốc tế)\M|\m(cổng jack [0-9\.]+|cổng type[-\s]*c|jack [0-9\.]+|jack 3 5|anc)\M|\m(magsafe|zolo|sạc nhanh)\M|\m(music)\M|\m((sạc\s*)?[0-9]+w|[0-9]+cpu|[0-9]+gpu|touch id|nano)\M|\m(creator bundle|essentials bundle|dual battery|bundle)\M|\m(nfc)\M',
                        '', 'g'
                    ),
                    '[\(\)\[\]\-\–\_\,\.\/\:\|\+\*\#\&\~\=\^\>\<]+', ' ', 'g'
                ),
                '\s+', ' ', 'g'
            )
        ) AS raw_cleaned,
                TRIM(REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(
                                    REGEXP_REPLACE(
                                        REGEXP_REPLACE(
                                            REGEXP_REPLACE(
                                                REGEXP_REPLACE(
                                                    REGEXP_REPLACE(
                                                        REGEXP_REPLACE(
                                                            REGEXP_REPLACE(
                                                                REGEXP_REPLACE(
                                                                    REGEXP_REPLACE(
                                                                        REGEXP_REPLACE(
                                                                            REGEXP_REPLACE(
                                                                                REGEXP_REPLACE(
                                                                                    REGEXP_REPLACE(
                                                                                        REGEXP_REPLACE(
                                                                                            REGEXP_REPLACE(
                                                                                                REGEXP_REPLACE(
                                                                                                    REGEXP_REPLACE(
                                                                                                        REGEXP_REPLACE(
                                                                                                            REGEXP_REPLACE(
                                                                                                                REGEXP_REPLACE(
                                                                                                                    REGEXP_REPLACE(
                                                                                                                        REGEXP_REPLACE(
                                                                                                                            REGEXP_REPLACE(
                                                                                                                                REGEXP_REPLACE(
                                                                                                                                    product_name,
                                                                                                                                    '\s*\([^\)]*\)', '', 'g'
                                                                                                                                ),
                                                                                                                                '\s*\|.*$', '', 'g'
                                                                                                                            ),
                                                                                                                            '\s+\mI\M\s+chính hãng.*$', '', 'i'
                                                                                                                        ),
                                                                                                                        '\s*\((hàng\s*chính hãng|chính hãng|nhập khẩu)\)', '', 'i'
                                                                                                                    ),
                                                                                                                    '\s+(chính hãng\s*apple\s*việt\s*nam|chính hãng\s*việt\s*nam|chính hãng\s*vn\/a|nhập khẩu\s*chính hãng|hàng\s*chính hãng|chính hãng|vn\/a|nhập khẩu)\s*$', '', 'i'
                                                                                                                ),
                                                                                                                '[-–\s]*(công\s*thái\s*học|ergonomic|ergo)\M', '', 'i'
                                                                                                            ),
                                                                                                            '\s*(black|white|đen|trắng)?/(?:ch|ap)-[0-9a-z\-]+', '', 'i'
                                                                                                        ),
                                                                                                        '/(?:ch|ap)-[0-9a-z\-]+', '', 'i'
                                                                                                    ),
                                                                                                    '\m(?:ch|ap)-[0-9a-z\-]+', '', 'i'
                                                                                                ),
                                                                                                '\s*[-–/]\s*(kem|xanh\s*da\s*trời|xanh\s*lá|xanh\s*dương|xanh\s*rêu|xanh\s*gốm|xanh\s*navy|xanh\s*cổ\s*vịt|xanh|đen|trắng|đỏ|tím|vàng|hồng|xám\s*(đậm|bạc|đen|nhạt|trắng)?|xám|cam|nâu|be|ghi|bạc|kim|black|white|blue|green|red|purple|yellow|pink|orange|brown|gray|grey|silver|gold|tuxedo|midnight|starlight|space\s*gray|graphite)(\s*mẫu\s*mới)?\s*$', '', 'i'
                                                                                            ),
                                                                                            '\s+\m(graphite|tuxedo|mẫu\s*mới)\M\s*$', '', 'i'
                                                                                        ),
                                                                                        '\s*[\(\[\-–,]?\s*\m(kèm|tặng\s*kèm|tích\s*hợp)\s+[^\)\]]*[\)\]]?', '', 'i'
                                                                                    ),
                                                                                    '\s*\m(kiêm\s+adapter\s*sạc|kiêm\s+sạc|kiêm\s+pin\s*dự\s*phòng)\M', '', 'i'
                                                                                ),
                                                                                '\s*[-–]?\s*\m(chủ\s*động\s*khử\s*tiếng\s*ồn|chống\s*ồn\s*chủ\s*động|chống\s*ồn|khử\s*tiếng\s*ồn)\M', '', 'i'
                                                                            ),
                                                                            '\s*\+\s*Touch\s*ID\M', ' Touch ID', 'i'
                                                                        ),
                                                                        '\s*\+\s*Trackpad\M', ' Trackpad', 'i'
                                                                    ),
                                                                    '\s*\+\s*Cellular\M', ' Cellular', 'i'
                                                                ),
                                                                '\s*\+\s*2\.4G.*$', '', 'i'
                                                            ),
                                                            '\s*\+\s*chống\s*nước.*$', '', 'i'
                                                        ),
                                                        '\s*\+\s*cáp.*$', '', 'i'
                                                    ),
                                                    '\m4\s*viên\s*pin\s*AA\s*\+\s*4\s*viên\s*pin\s*AAA\M', '4 pin AA và 4 pin AAA', 'i'
                                                ),
                                                '\mStreamDeck\s*\+\M', 'StreamDeck Plus', 'i'
                                            ),
                                            '\s+và\s+usb\M', '', 'i'
                                        ),
                                        '^(bàn\s*phím\s*[\+\&]\s*bao\s*da|bao\s*da\s*(kèm\s*|kiêm\s*)?bàn\s*phím|bàn\s*phím\s*kiêm\s*bao\s*da)\s*', 'Bàn Phím Bao Da ', 'i'
                                    ),
                                    '\m(bàn\s*phím\s*[\+\&]\s*bao\s*da|bao\s*da\s*(kèm\s*|kiêm\s*)?bàn\s*phím|bàn\s*phím\s*kiêm\s*bao\s*da)\M', 'Bàn phím bao da', 'i'
                                ),
                                '^(chuột\s+)?(combo\s*bàn\s*phím\s*[\+\&]\s*chuột|bộ\s*bàn\s*phím\s*[\+\&]\s*chuột|bộ\s*bàn\s*phím\s*(và\s*)?chuột|combo\s*bàn\s*phím\s*(và\s*)?chuột|bàn\s*phím\s*[\+\&]\s*chuột|bàn\s*phím\s*và\s*chuột)\s*', 'Bộ Bàn Phím Chuột ', 'i'
                            ),
                            '\m(combo\s*bàn\s*phím\s*[\+\&]\s*chuột|bộ\s*bàn\s*phím\s*[\+\&]\s*chuột|bộ\s*bàn\s*phím\s*(và\s*)?chuột|combo\s*bàn\s*phím\s*(và\s*)?chuột|bàn\s*phím\s*[\+\&]\s*chuột|bàn\s*phím\s*và\s*chuột)\M', 'Bộ bàn phím chuột', 'i'
                        ),
                        '\s*[\+\&]\s*chuột(\s+logitech|\s+apple)?\M', ' ', 'i'
                    ),
                    '\s+\+\s+', ' ', 'g'
                ),
                '\m(Veekos\s+K75|Core\s+5)\s+\1\M', '\1', 'i'
            ),
            '\s+', ' ', 'g'
        )) AS cleaned_name
    FROM distinct_products
        WHERE NOT (
            (
                product_name ~* '\m(túi\s*(đựng\s*|lọc\s*|chứa\s*|gom\s*)?(rác|bụi)|hộp\s*chứa\s*bụi|hộp\s*nước|giẻ\s*lau|khăn\s*lau|tấm\s*lau|nước\s*lau|chổi\s*(chính|phụ|quét|cuộn|cạnh)|con\s*lăn\s*phụ\s*kiện)\M'
                OR product_name ~* '^(bộ|combo)\s*[0-9]*\s*(túi\s*(đựng\s*|lọc\s*|chứa\s*|gom\s*)?(rác|bụi)|chổi|giẻ|khăn|phụ\s*kiện)'
                OR (LOWER(TRIM(category)) = 'vacuum' AND (
                    product_name ~* '\m(màng\s*lọc|lõi\s*lọc|bộ\s*lọc\s*bụi|bộ\s*lọc\s*thay\s*thế|bộ\s*phụ\s*kiện|hộp\s*phụ\s*kiện)\M'
                    OR product_name ~* '^(bộ\s*[0-9]+\s*túi|tấm\s*màng|chổi\s*cho|bộ\s*phụ\s*kiện|hộp\s*phụ\s*kiện|con\s*lăn\s*phụ\s*kiện)'
                ))
            )
            OR (LOWER(TRIM(category)) = 'camera' AND (
                product_name ~* '\m(ngàm|chân\s*gắn|gậy\s*(chụp|tự\s*sướng|selfie)|tripod|dây\s*đeo\s*(ngực|đầu|cổ|tay)|khung\s*bảo\s*vệ|vỏ\s*bảo\s*vệ|vỏ\s*chống\s*nước|chuông\s*cửa|pin\s*cho\s*gopro|sạc\s*pin|hộp\s*sạc\s*pin|dock\s*sạc)\M'
                OR product_name ~* '^(bộ\s*ngàm|chân\s*gắn|bộ\s*chuông|gậy\s*selfie|gậy\s*chụp)'
            ))
            OR (LOWER(TRIM(category)) = 'smartwatch' AND (
                product_name ~* '^(dây\s*đeo|dây\s*thay\s*thế|dây\s*đồng\s*hồ|dây\s*quickfit|dây\s*quick\s*release)'
                OR product_name ~* '\m(dây\s*thay\s*thế|dây\s*quickfit|dây\s*quick\s*release)\M'
                OR product_name ~* '^dây\s+(apple\s*watch|garmin|silicone|cao\s*su|da|thép|vải|sport|milanese)'
            ))
            OR (LOWER(TRIM(category)) = 'air-purifier' AND (
                product_name ~* '\m(lõi\s*lọc|màng\s*lọc|bộ\s*lọc\s*thay\s*thế|tấm\s*lọc|khung\s*treo)\M'
            ))
            OR (LOWER(TRIM(category)) = 'tivi' AND (
                product_name ~* '\m(khung\s*treo|giá\s*treo|kệ\s*treo)\M'
            ))
            OR (LOWER(TRIM(category)) = 'monitor' AND (
                product_name ~* '\m(giá\s*treo|arm\s*màn\s*hình)\M'
                AND NOT product_name ~* '\m(màn\s*hình|display)\s+[0-9]+'
            ))
            OR (LOWER(TRIM(category)) IN ('keyboard', 'mouse') AND (
                product_name ~* '\m(lót\s*chuột|pad\s*chuột|bàn\s*di\s*chuột|kê\s*tay|keycap|switch\s*lẻ)\M'
                OR product_name ~* '^(chuột\s*có$|chuột\s*chơi\s*game\s*co$|chuột\s*$)'
            ))
        )
    ),

    cleaned_names AS MATERIALIZED (
        SELECT
            product_name,
            category,
            REGEXP_REPLACE(raw_cleaned, '(?i)\s*mẫu\s*mới', '', 'g') AS raw_cleaned,
            REGEXP_REPLACE(
            REGEXP_REPLACE(
            REGEXP_REPLACE(
            REGEXP_REPLACE(
            REGEXP_REPLACE(
            REGEXP_REPLACE(
            REGEXP_REPLACE(
                cleaned_name,
                '(?i)\s*mẫu\s*mới', '', 'g'),
                '[-–\s]*(có\s*mic|kèm\s*mic|tích\s*hợp\s*mic|không\s*mic|có\s*micro|kèm\s*micro)\M', '', 'gi'),
                '[-–\s]*(choàng\s*đầu)\M', '', 'gi'),
                '\s*màu\s*(đen|trắng|xanh|đỏ|tím|vàng|hồng|xám|cam|nâu|be|ghi|bạc|kim|black|white|blue|green|red|purple|yellow|pink|orange|brown|gray|grey|silver|gold|bóng\s*đêm)\M', '', 'gi'),
                '[-–/,\s]+(xanh\s*dương\s*trắng\s*tím\s*đậm|xanh\s*lá\s*đen|xanh\s*dương\s*trắng|xanh\s*trắng|trắng\s*xanh|cyan\s*blue|yellow\s*blue|xanh\s*bóng\s*đêm|vàng\s*hồng|vàng\s*đồng|xám\s*bạc|xám\s*đen|đen\s*trắng\s*đỏ|đen\s*trắng|trắng\s*đen|hồng\s*trắng|trắng\s*hồng|pink\s*white|white\s*black|black\s*white|white\s*pink|pink\s*black|black\s*pink|jelly\s*pink|sakura\s*pink|grey\s*black|black\s*grey|gray\s*black|black\s*gray|rose\s*gold|rosegold|quartz)(\s+gradient)?\s*$', '', 'i'),
                '[-–/,\s]+gradient\s*$', '', 'i'),
                '[-–/,\s]+(kem|xanh\s*da\s*trời|xanh\s*lá|xanh\s*dương|xanh\s*rêu|xanh\s*gốm|xanh\s*navy|xanh\s*cổ\s*vịt|xanh|đen|trắng|đỏ|tím|vàng|hồng|xám|cam|nâu|be|ghi|bạc|kim|black|white|blue|green|red|purple|yellow|pink|orange|brown|gray|grey|silver|gold|tuxedo|midnight|starlight|space\s*gray|graphite)\s*$', '', 'i') AS cleaned_name
        FROM cleaned_catalog_base
    ),

    cleaned_catalog_raw AS MATERIALIZED (
    SELECT
        product_name,
        category,
            CASE
        WHEN cleaned_name ~* '^(bộ\s*bàn\s*phím|combo\s*bàn\s*phím|bàn\s*phím\s*và\s*chuột)' THEN
            'Bộ Bàn Phím Chuột ' || TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(cleaned_name, '^(bộ\s*bàn\s*phím\s*chuột|combo\s*bàn\s*phím\s*chuột|bộ\s*bàn\s*phím|combo\s*bàn\s*phím|bàn\s*phím\s*chuột|bàn\s*phím\s*và\s*chuột)\s*', '', 'i'),
                '\m(bluetooth|không\s*dây|có\s*dây|gaming|chơi\s*game|silent)\M', '', 'gi'
            ))
        WHEN cleaned_name ~* '^bàn\s*phím\s*bao\s*da' THEN
            'Bàn Phím Bao Da ' || TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(cleaned_name, '^bàn\s*phím\s*bao\s*da\s*', '', 'i'),
                '\m(bluetooth|không\s*dây|có\s*dây)\M', '', 'gi'
            ))
        WHEN category = 'mouse' THEN 
            'Chuột ' || TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(cleaned_name, '^(chuột|chuột)\s+', '', 'i'),
                '\m(chơi\s*game|gaming|silent|sạc|không\s*dây|có\s*dây|tcó\s*dây|bluetooth|wireless|công\s*thái\s*học|ergonomic)\M', '', 'gi'
            ))
        WHEN category = 'keyboard' THEN 
            'Bàn Phím ' || TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(
                                    cleaned_name,
                                    '\s*[\(\[\-–,]?\s*(blue|red|brown|black|yellow|green|white|cream(\s+yellow)?|wood(\s+v3)?|ice\s+crystal|magnetic|linear|tactile|clicky|silent|gateron|kailh|cherry(\s+mx)?|akko|piano|pro)?\s*(switches|switch|sw)\M.*$', '', 'i'
                                ),
                                '\s*[\(\[\-–,]?\s*(red|blue|white|rgb)?\s*(backlight|backlit|rgb\s*led|rgb)\M.*$', '', 'i'
                            ),
                            '\s*[\(\[\-–,]?\s*(world\s*tour(\s*viet\s*nam)?|dracula\s*castle|prunus\s*lannesiana(t)?|bun\s*wonderland|matcha\s*red\s*bean(\s*stellar\s*rose)?|horizon(\s*mirror)?|mirror(\s*[0-9]+)?|ice\s*cream(\s*pink)?|frost(\s*pink)?|green\s*ink|glacier\s*blue|sky\s*blue|ocean\s*star|phantom\s*green(\s*edition)?|white\s*edition|black\s*edition|storm|snow|gradient|rainbow|iceflow|piano|akko\s*piano|tri-mode|tenkeyless|mechanical)\M.*$', '', 'i'
                        ),
                        '\s*[\(\[\-–,]?\s*(black\s*(&|\+|và)?\s*gold|black\s*(&|\+|và)?\s*cyan|black\s*(&|\+|và)?\s*pink|black\s*(&|\+|và)?\s*gray|black\s*(&|\+|và)?\s*grey|black\s+on\s+white|white\s*(&|\+|và)?\s*purple|white\s*(&|\+|và)?\s*pink|white\s+cream)\M.*$', '', 'i'
                    ),
                    '^(bàn\s*phím|bàn\s*phím)\s+', '', 'i'
                ),
                '\m(cơ\s*không\s*dây|cơ\s*có\s*dây|không\s*dây|có\s*dây|bluetooth|wireless|cơ|giả\s*cơ|mechanical|gaming|tenkeyless|tri-mode|công\s*thái\s*học|ergonomic)\M', '', 'gi'
            ))
        WHEN category = 'smartwatch' THEN
            'Đồng Hồ ' || TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        cleaned_name,
                        '\s+\m(dây\s+(silicone|silicon|cao\s*su(\s+fluoro)?|thể\s*thao|nylon(\s+dệt)?|milanese|milan|da|thép|woven))\M.*$', '', 'i'
                    ),
                    '\s+\mviền\s+.*$', '', 'i'
                ),
                '^(đồng\s*hồ\s*thông\s*minh|đồng\s*hồ|đồng\s*hồ|vòng\s*đeo\s*tay\s*thông\s*minh|vòng\s*đeo\s*tay|smartwatch)\s*', '', 'i'
            ))
        WHEN category = 'headphone' THEN 
            'Tai Nghe ' || TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(cleaned_name, '^(tai nghe|headphone|earphone)\s+', '', 'i'),
                '\m(bluetooth|true\s*wireless|tws|không\s*dây|có\s*dây|chụp\s*tai|nhét\s*tai|in-ear|on-ear|over-ear|gaming|chơi\s*game)\M', '', 'gi'
            ))
        WHEN category = 'laptop' THEN 'Laptop ' || REGEXP_REPLACE(cleaned_name, '^(laptop|máy tính xách tay)\s+', '', 'i')
        WHEN category = 'monitor' AND NOT cleaned_name ~* '^(mac mini|mac studio)' THEN 'Màn Hình ' || REGEXP_REPLACE(cleaned_name, '^(màn hình|màn hình)\s+', '', 'i')
        WHEN category = 'tivi' THEN 'Tivi ' || REGEXP_REPLACE(cleaned_name, '^(tivi|google tivi|android tivi|smart tivi|smart tv|android tv|google tv|tv)\s+', '', 'i')
        WHEN category = 'mobile' THEN 'Điện Thoại ' || REGEXP_REPLACE(cleaned_name, '^(điện thoại|điện thoại|dtdd|smartphone)\s+', '', 'i')
        WHEN category = 'tablet' THEN 'Máy Tính Bảng ' || REGEXP_REPLACE(cleaned_name, '^(máy tính bảng|máy tính bảng|tablet)\s+', '', 'i')
        WHEN category = 'speaker' THEN 'Loa ' || REGEXP_REPLACE(cleaned_name, '^(loa|bộ loa|bộ loa|dàn loa|dàn âm thanh|soundbar|mic karaoke|combo loa)\s+', '', 'i')
        WHEN category = 'powerbank' THEN 'Pin Sạc Dự Phòng ' || REGEXP_REPLACE(cleaned_name, '^(pin sạc dự phòng(\s+di\s+động)?|pin sạc dự phòng|sạc dự phòng|pin dự phòng|trạm sạc(\s+dự\s+phòng)?|đế sạc|củ sạc|dự\s+phòng(\s+di\s+động)?)\s+', '', 'i')
        WHEN category = 'air-purifier' THEN 'Máy Lọc Không Khí ' || REGEXP_REPLACE(cleaned_name, '^(máy lọc không khí|máy lọc|robot lọc)\s+', '', 'i')
        WHEN category = 'vacuum' THEN 
            CASE WHEN cleaned_name ~* 'robot' THEN 'Robot Hút Bụi ' || REGEXP_REPLACE(cleaned_name, '^(robot hút bụi lau nhà|robot hút bụi|robot)\s+', '', 'i') ELSE 'Máy Hút Bụi ' || REGEXP_REPLACE(cleaned_name, '^(máy hút bụi|máy lau)\s+', '', 'i') END
        WHEN category = 'camera' THEN 'Camera ' || REGEXP_REPLACE(cleaned_name, '^(camera|webcam)\s+', '', 'i')
        ELSE cleaned_name
    END AS display_name_raw,
            TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            CASE
                WHEN category = 'powerbank' THEN 'pin sạc dự phòng ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(raw_cleaned, '^(pin sạc dự phòng|sạc dự phòng|pin dự phòng|trạm sạc|bộ hộp sạc)\s*', ''),
                                '\m(zolo|magsafe|polymer|spark mini|enerfill|powermag|switch|ia20pd|e0027s)\M', '', 'g'
                            ),
                            '\m(kèm cáp.*|tích hợp cáp.*|có chân đứng.*|cổng usb.*)\M', '', 'g'
                        ),
                        '\s+', ' ', 'g'
                    )
                WHEN category = 'camera' THEN 'camera ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(raw_cleaned, '^(camera|camera hành trình|camera hành động|camera an ninh|camera quan sát|camera giám sát|bộ chuông cửa|chuông cửa|bộ kit|bộ tay cầm|bộ ngàm|bộ insta360)\s*', ''),
                            '\m(360 độ|ngoài trời|trong nhà|an ninh|quan sát|giám sát|wifi|ip|cs-|g1|triple|2k\+|[0-9]+mp)\M', '', 'g'
                        ),
                        '\s+', ' ', 'g'
                    )
                WHEN category = 'speaker' AND NOT raw_cleaned ~* '^(loa|bộ loa|dàn loa|dàn âm thanh)' THEN 'loa ' || REGEXP_REPLACE(raw_cleaned, '^bộ\s+', '')
                WHEN category = 'air-purifier' AND NOT raw_cleaned ~* '^(bộ lọc|màng lọc|lõi lọc)' THEN 'máy lọc không khí ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(raw_cleaned, '^(máy lọc không khí|máy lọc|robot lọc)\s*', ''),
                            '\m(mẫu mới|thông minh|tạo ẩm|hút ẩm|[0-9]+w)\M', '', 'g'
                        ),
                        '\s+', ' ', 'g'
                    )
                WHEN category = 'headphone' THEN 
                    'tai nghe ' || TRIM(REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(
                                    REGEXP_REPLACE(raw_cleaned, '^tai nghe\s+', ''),
                                    '\m(wh|wf)[-\s]*([0-9]+xm[0-9]+|ch[0-9]+|lc[0-9]+)\M', '\1\2', 'g'
                                ),
                                '^airpods\M', 'apple airpods'
                            ),
                            '\m(bluetooth|true wireless|tws|open-ear|ows|không dây|có dây|chụp tai|nhét tai|choàng đầu|in-ear|on-ear|over-ear)\M', '', 'gi'
                        ),
                        '\s+', ' ', 'g'
                    ))
                WHEN category = 'mouse' THEN 
                    'chuột ' || TRIM(REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                CASE WHEN raw_cleaned ~* '^(chuột|combo)' THEN raw_cleaned ELSE 'chuột ' || REGEXP_REPLACE(raw_cleaned, '^(chuột|chuột)\s*', '') END,
                                '\mgen\s*2\s+lightsync\M', 'lightsync', 'g'
                            ),
                            '\m(không dây|có dây|bluetooth|wireless|gaming|sạc không dây|quang học|công thái học|ergonomic)\M', '', 'gi'
                        ),
                        '\s+', ' ', 'g'
                    ))
                WHEN category = 'monitor' THEN 'màn hình ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(raw_cleaned, '^màn hình\s+', ''),
                                '\m(ls[0-9]{2}[a-z0-9]+)(gaexxv|eexxv|xxv)\M', '\1', 'g'
                            ),
                            '\m(s30gd|s3|fhd|qhd|ips|va|tn|[0-9]+hz|[0-9]+(\.[0-9]+)?\s*inch|full\s*hd)\M', '', 'g'
                        ),
                        '\s+', ' ', 'g'
                    )
                WHEN category = 'vacuum' THEN 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            CASE WHEN raw_cleaned ~* 'robot' THEN 'robot hút bụi ' || REGEXP_REPLACE(raw_cleaned, '^(robot hút bụi lau nhà|robot hút bụi|robot)\s*', '') ELSE 'máy hút bụi ' || REGEXP_REPLACE(raw_cleaned, '^(máy hút bụi|máy lau)\s*', '') END,
                            '\m(eumẫu mới|mẫu mới|eu|global|quốc tế|bản quốc tế|tự động làm sạch|lau sàn|lau nhà|prime|ultra|omni|heat|gen\s*[0-9\.]+|bhr[0-9a-z]+)\M', '', 'g'
                        ),
                        '\s+', ' ', 'g'
                    )
                WHEN category = 'keyboard' THEN 
                    TRIM(REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                CASE WHEN raw_cleaned ~* '^(bộ bàn phím|combo)' THEN raw_cleaned ELSE 'bàn phím ' || REGEXP_REPLACE(raw_cleaned, '^(bàn phím|bàn phím)\s*', '') END,
                                '\m(cơ không dây|cơ có dây|không dây|có dây|bluetooth|wireless|cơ|giả cơ|mechanical|gaming|tri-mode|tenkeyless|keyboard|công thái học|ergonomic)\M', '', 'gi'
                            ),
                            '\m(world tour|viet nam|dracula castle|prunus lannesiana|bun wonderland|matcha red bean|stellar rose|horizon mirror|horizon|mirror\s*[0-9]*|ice cream|frost pink|frost|green ink|glacier blue|sky blue|ocean star|phantom green|white edition|black edition|storm|snow|gradient|rainbow|iceflow|piano|cyan|akko piano|gold|m704|cream|white\s*cream|graphite|pink\s*white|white\s*black|black\s*white|quartz|jelly\s*pink|sakura\s*pink|vàng\s*hồng|xám\s*đen|xanh\s*lá\s*đen|xanh\s*bóng\s*đêm|cyan\s*blue|yellow\s*blue|xanh\s*dương\s*trắng)\M', '', 'gi'
                        ),
                        '\s+', ' ', 'g'
                    ))
                WHEN category = 'tivi' THEN 'tivi ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(
                                    REGEXP_REPLACE(raw_cleaned, '\m([0-9]{2}(?:qn|q|m|du|cu|au|tu)[0-9]+h)a\M', '\1', 'g'),
                                    '\m(ua|qa|kd|k)\s*([0-9]{2}[a-z0-9]+)\M', '\2', 'g'
                                ),
                                '\m(bravia\s*[0-9]+|smart ai tv|smart tivi|google tivi|android tivi|smart tv|google tv|android tv|tivi|tv|tcl ai|evo)\M', '', 'g'
                            ),
                            '\m(smart\s*ai|ai|ii|iii|iv)\M', '', 'g'
                        ),
                        '\s+', ' ', 'g'
                    )
                WHEN category = 'mobile' THEN 'điện thoại ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(
                                    REGEXP_REPLACE(raw_cleaned, '^(điện thoại di động|điện thoại|dtdd)\s+', '', 'i'),
                                    '\msamsung\s+(?:galaxy\s+)?a([0-9]{2}[a-z]?)\M', 'samsung galaxy a\1', 'g'
                                ),
                                '\mreno\s*([0-9]+)\M', 'reno\1', 'g'
                            ),
                            '\mredmi\s+note\s*([0-9]+)\M', 'redmi note \1', 'g'
                        ),
                        '([0-9]+gb)/([0-9]+gb)', '\1 \2', 'g'
                    )
                WHEN category = 'tablet' THEN 'máy tính bảng ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(raw_cleaned, '^(máy tính bảng|tablet)\s+', '', 'i'),
                            '([0-9]+gb)/([0-9]+gb)', '\1 \2', 'g'
                        ),
                        '\m(wifi|cellular|5g|4g|lte)\M', '', 'g'
                    )
                WHEN category = 'smartwatch' THEN 'đồng hồ ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(raw_cleaned, '^(đồng hồ thông minh|đồng hồ|smartwatch)\s+', '', 'i'),
                            '\m(dây)\M', '', 'g'
                        ),
                        '([0-9]+)\s*mm\M', '\1mm', 'g'
                    )
                WHEN category = 'laptop' THEN 'laptop ' || 
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                CASE
                                    WHEN raw_cleaned ~* 'aspire\s+lite\s+14' THEN 'acer aspire lite 14'
                                    WHEN raw_cleaned ~* 'aspire\s+lite\s+15' THEN 'acer aspire lite 15'
                                    WHEN raw_cleaned ~* 'aspire\s+lite\s+16' THEN 'acer aspire lite 16'
                                    WHEN raw_cleaned ~* 'aspire\s+go\s+14' THEN 'acer aspire go 14'
                                    WHEN raw_cleaned ~* 'aspire\s+go\s+15' THEN 'acer aspire go 15'
                                    WHEN raw_cleaned ~* 'aspire\s+5' THEN 'acer aspire 5'
                                    WHEN raw_cleaned ~* 'aspire\s+7' THEN 'acer aspire 7'
                                    WHEN raw_cleaned ~* 'nitro\s+lite\s+16' THEN 'acer nitro lite 16'
                                    WHEN raw_cleaned ~* '(nitro\s+16|an16)' THEN 'acer nitro 16'
                                    WHEN raw_cleaned ~* '(nitro\s+v\s*15|anv15)' THEN 'acer nitro v15'
                                    WHEN raw_cleaned ~* '^laptop\s+' THEN REGEXP_REPLACE(raw_cleaned, '^laptop\s+', '')
                                    ELSE raw_cleaned
                                END,
                                '\m(13|14|15|16)\s+(m[1-9]|a18)\M', '\2', 'g'
                            ),
                            '\m(gaming|oled|ultra\s*[0-9]+[a-z]*|core\s*[0-9]+[a-z]*|r[0-9]+[a-z]*|i[3579][0-9]*[a-z]*|ram\s*[0-9]+gb|[0-9]+gb\s*ram|[0-9]{3,5}(?:hx|hs|[uhsv])|u[3579]|hx|hs|ai|flip|2y|27|5|umc|w11blu|w11slu|w11ibd2)\M|\m(amd|ryzen)?\s*(ai|al)?\s*[0-9]\s+[0-9]{2,3}\M', '', 'g'
                        ),
                        '\s+', ' ', 'g'
                    )
                ELSE raw_cleaned
            END,
            '^bàn phím\s+bộ bàn phím', 'bộ bàn phím'
        ),
        '\s+', ' ', 'g'
    )) AS match_key_raw
    FROM cleaned_names
),

cleaned_catalog AS MATERIALIZED (
    SELECT
        r.product_name,
        r.category,
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
        REGEXP_REPLACE(
            strip_trailing_colors(title_case_preserve(r.display_name_raw)),
            '(?i)\m(led)\M', 'LED', 'g'),
            '(?i)\m(inzone)\M', 'INZONE', 'g'),
            '(?i)\m(tkl)\M', 'TKL', 'g'),
            '(?i)\m(rgb)\M', 'RGB', 'g'),
            '(?i)\m(usb)\M', 'USB', 'g'),
            '(?i)\m(4k)\M', '4K', 'g'),
            '(?i)\m(8k)\M', '8K', 'g'),
            '(?i)\m(fhd)\M', 'FHD', 'g'),
            '(?i)\m(qhd)\M', 'QHD', 'g'),
            '(?i)\m(uhd)\M', 'UHD', 'g'),
            '(?i)\m(oled)\M', 'OLED', 'g'),
            '(?i)\m(qled)\M', 'QLED', 'g'),
            '(?i)\m(qned)\M', 'QNED', 'g'),
            '(?i)\m(hd)\M', 'HD', 'g'),
            '(?i)\m(ai)\M', 'AI', 'g'),
            '(?i)\m(inch)\M', 'Inch', 'g'),
            '(?i)\m(mini)\M', 'Mini', 'g'),
            '(?i)\m(smart\s*tv)\M', 'Smart TV', 'g'),
            '(?i)\m(macbook)\M', 'MacBook', 'g'),
            '(?i)\m(ipad)\M', 'iPad', 'g'),
            '(?i)\m(iphone)\M', 'iPhone', 'g'),
            '(?i)\m(airpods)\M', 'AirPods', 'g'),
            '(?i)\m(pro)\M', 'Pro', 'g'),
            '(?i)\m(plus)\M', 'Plus', 'g'),
            '(?i)\m(max)\M', 'Max', 'g'),
            '(?i)\m(ultra)\M', 'Ultra', 'g'),
            '(?i)\m(lite)\M', 'Lite', 'g'),
            '(?i)\m(series)\M', 'Series', 'g'),
            '(?i)\m(wifi)\M', 'Wifi', 'g'),
            '(?i)\m(karaoke)\M', 'Karaoke', 'g') AS clean_product_name,
        strip_trailing_colors(r.match_key_raw) AS match_key_raw
    FROM cleaned_catalog_raw r
)

SELECT
    r.product_id AS site_product_id,
    c.clean_product_name AS product_name,
    UPPER(TRIM(r.brand)) AS brand,
    c.category,
    NULLIF(REGEXP_REPLACE(r.current_price, '[^0-9]', '', 'g'), '')::BIGINT AS current_price,
    NULLIF(REGEXP_REPLACE(r.original_price, '[^0-9]', '', 'g'), '')::BIGINT AS original_price,
    COALESCE(NULLIF(REGEXP_REPLACE(r.discount_percent, '[^0-9]', '', 'g'), '')::INTEGER, 0) AS discount_percent,
    r.availability,
    INITCAP(TRIM(r.store_name)) AS store_name,
    COALESCE(r.location_code, 'HN') AS location_code,
    COALESCE(r.province_name, 'Thành phố Hà Nội') AS province_name,
    COALESCE(r.region, 'Miền Bắc') AS region,
    r.promotions,
    r.product_url,
    r.image_url,
    r.rating,
    r.review_count,
    r.crawl_time,
    c.match_key_raw
FROM {{ source('raw', 'raw_products') }} r
JOIN cleaned_catalog c
  ON r.product_name = c.product_name
 AND r.category = c.category
