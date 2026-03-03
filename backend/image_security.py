import cv2
import numpy as np

def compare_images(img1_path, img2_path):
    # 1. படங்களை லோட் செய்தல்
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)

    if img1 is None or img2 is None:
        return 0.0

    # 2. படங்களை ஒரே அளவிற்கு மாற்றுதல்
    img1 = cv2.resize(img1, (500, 500))
    img2 = cv2.resize(img2, (500, 500))

    # 3. ORB Detector உருவாக்குதல் (இதுதான் நிஜமான AI அம்சம்)
    # இது பொருளின் முக்கிய அடையாளங்களை (Features) கண்டுபிடிக்கும்
    orb = cv2.ORB_create(nfeatures=1000)

    # Keypoints மற்றும் Descriptors-ஐக் கண்டறிதல்
    kp1, des1 = orb.detectAndCompute(img1, None)
    kp2, des2 = orb.detectAndCompute(img2, None)

    if des1 is None or des2 is None:
        return 0.0

    # 4. Brute-Force Matcher பயன்படுத்தி ஒப்பிடுதல்
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)

    # 5. ஒற்றுமையின் அடிப்படையில் வரிசைப்படுத்துதல்
    matches = sorted(matches, key=lambda x: x.distance)

    # 6. Similarity Score கணக்கிடுதல்
    # எத்தனை புள்ளிகள் மேட்ச் ஆகிறது என்பதை வைத்து ஸ்கோர் தருகிறோம்
    match_count = len(matches)
    # பொதுவாக 1000 புள்ளிகளில் 150-க்கு மேல் மேட்ச் ஆனாலே அது அதே பொருள்தான்
    score = (match_count / 300) * 100 
    
    if score > 100: score = 100.0

    return round(score, 2)