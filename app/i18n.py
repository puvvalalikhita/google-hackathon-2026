"""Multilingual language detection, normalization & reply templates for DeliverEx Live.

Supported conversation languages (codes):
  en        English
  hinglish  Hinglish (romanized Hindi + English)
  hi        Hindi (Devanagari)
  tanglish  Tanglish (romanized Tamil + English)
  ta        Tamil (Tamil script)
  tenglish  Tenglish (romanized Telugu + English)
  te        Telugu (Telugu script)
"""
import re
from typing import Any, Dict, Optional, Tuple

LANG_CODES = ("en", "hinglish", "hi", "tanglish", "ta", "tenglish", "te")

LANG_LABELS: Dict[str, str] = {
    "en": "English",
    "hinglish": "Hinglish (HI+EN)",
    "hi": "Hindi (HI)",
    "tanglish": "Tanglish (TA+EN)",
    "ta": "Tamil (TA)",
    "tenglish": "Tenglish (TE+EN)",
    "te": "Telugu (TE)",
}

DEFAULT_LANG = "hinglish"

_HINGLISH_MARKERS = {
    "hai", "hain", "kar", "karo", "kiya", "diya", "liya", "mila", "mil", "gaya", "gayi", "gaye",
    "kitna", "kitne", "bata", "batao", "bataiye", "bhej", "bhejo", "maang", "aaj", "ruko", "bhai",
    "chahiye", "se", "pe", "aur", "nahi", "nahin", "haan", "haanji", "hanji", "ji", "kya", "kaise",
    "kaisa", "hoon", "hu", "mein", "ka", "ki", "ke", "ko", "wala", "wale", "abhi", "theek", "thik",
    "accha", "achha", "acha", "bolo", "karwa", "dena", "de", "uncle", "paisa", "paise", "rupaye",
    "bori", "phate", "phata", "kharab", "namaste", "shukriya", "dhanyawad", "haal", "sab", "yaar",
    "baki", "baaki", "hisaab", "chhoot", "dijiye", "kijiye", "raha", "rahe", "rahi", "hua", "hue",
}

_TANGLISH_MARKERS = {
    "anna", "akka", "pannitten", "panniten", "pannunga", "panren", "pannuren", "kedaichu",
    "kedaichuduchu", "kedachiruchu", "aayiduchu", "aachu", "anuppunga", "anuppitten", "vandhuruchu",
    "seri", "illa", "illai", "romba", "enna", "epdi", "eppadi", "sollunga", "solunga", "vanakkam",
    "nandri", "irukku", "irukken", "kudunga", "theriyuma", "venum", "vendam", "podunga", "paarunga",
    "machan", "pesunga", "paathukonga",
}

_TENGLISH_MARKERS = {
    "unnaru", "unnav", "unnanu", "unnadi", "bagunnara", "bagunnava", "bagunna", "bagunnanu", "ela",
    "enti", "emiti", "cheppandi", "cheppu", "cheyyandi", "cheyyi", "chesanu", "chesa", "chesaru",
    "icharu", "ichadu", "ichindi", "vachindi", "vachayi", "andi", "garu", "avunu", "sare", "ledu",
    "vaddu", "dabbulu", "dabbu", "bastalu", "basta", "sanchulu", "namaskaram", "dhanyavadalu", "kavali",
    "undi", "unnayi", "pampandi", "pampanu", "ayyindi", "ayyayi", "matladandi", "matladu", "nenu",
    "meeru", "evaru", "ekkada", "ippudu", "inka", "chala", "baaga", "dukanam",
    "naaku", "naku", "bagoledu", "bagaledu", "baledu", "jwaram", "noppi", "varsham",
    "cheyyalekapoyanu", "cheyyaledu", "kaledu",
}

_AMBIGUOUS = {
    "ok", "okay", "yes", "no", "hello", "hi", "hey", "thanks", "thank", "you", "done", "cool",
    "great", "nice", "sure", "fine", "good", "hmm", "right", "yeah", "yep", "perfect", "please",
}

_SWITCH_PATTERNS = [
    ("tenglish", re.compile(r"\btenglish\b", re.I)),
    ("tanglish", re.compile(r"\btanglish\b", re.I)),
    ("hinglish", re.compile(r"\bhinglish\b", re.I)),
    ("te", re.compile(r"(?:\b(?:speak|talk|reply|answer|switch)\b.*\btelugu\b|\btelugu\s*(?:lo|lone|please|only|matladu|matladandi)\b|\bin telugu\b|తెలుగు)", re.I)),
    ("en", re.compile(r"(?:\b(?:speak|talk|reply|answer|switch)\b.*\benglish\b|\benglish\s*(?:mein|me|la|il|please|only)\b|\bin english\b|अंग्रेज़ी में|अंग्रेजी में|ஆங்கிலத்தில்)", re.I)),
    ("hi", re.compile(r"(?:\b(?:speak|talk|reply|answer|switch)\b.*\bhindi\b|\bhindi\s*(?:mein|me|main|please|only)\b|\bin hindi\b|हिंदी में|हिन्दी में)", re.I)),
    ("ta", re.compile(r"(?:\b(?:speak|talk|reply|answer|switch)\b.*\btamil\b|\btamil\s*(?:la|il|le|please|only|pesunga)\b|\bin tamil\b|தமிழ்)", re.I)),
]


_LANG_NAME_PATTERNS = [
    ("tenglish", re.compile(r"\btenglish\b", re.I)),
    ("tanglish", re.compile(r"\btanglish\b", re.I)),
    ("hinglish", re.compile(r"\bhinglish\b", re.I)),
    ("te", re.compile(r"\b(?:telugu|telgu|telegu|telagu|tellugu|thelugu|telugulo)\b|తెలుగు", re.I)),
    ("ta", re.compile(r"\b(?:tamil|thamizh|tamizh|thamil|tamilla|tamil-la)\b|தமிழ்", re.I)),
    ("hi", re.compile(r"\b(?:hindi|hindhi|hindime|hindimein)\b|हिंदी|हिन्दी", re.I)),
    ("en", re.compile(r"\b(?:english|inglish|angrezi|angreji|englishla|englishlo)\b|अंग्रेज़ी|अंग्रेजी|इंग्लिश|ஆங்கிலம்|ஆங்கிலத்தில்|இங்கிலீஷ்|ఇంగ్లీష్|ఆంగ్లం", re.I)),
]

_SWITCH_CUES = re.compile(
    r"\b(?:speak|talk|reply|respond|answer|switch|change|language|lang|use|want|prefer|can you|could you|"
    r"please|only|bolo|bol|bolna|boliye|baat|karo|kariye|mein|me|main|lo|lone|la|le|il|matladu|matladandi|"
    r"maatladu|matlade|pesu|pesunga|pesungal|pesuren|sollu|sollunga|cheppu|cheppandi|now|from now)\b"
    r"|भाषा|में|बोलो|बात|భాష|లో|మాట్లాడు|மொழி|பேசு|ல",
    re.I,
)


def _detect_switch_request(text: str) -> Optional[str]:
    """Detects 'speak Telugu / Hindi mein bolo / tamil la pesunga / change language to English' requests."""
    best_code, best_pos = None, -1
    for code, pat in _LANG_NAME_PATTERNS:
        for m in pat.finditer(text):
            if m.start() > best_pos:
                best_code, best_pos = code, m.start()
    if not best_code:
        return None
    if len(text.split()) <= 4 or _SWITCH_CUES.search(text):
        return best_code
    return None


def _count_script(text: str, lo: str, hi: str) -> int:
    return sum(1 for ch in text if lo <= ch <= hi)


def detect_language(raw_text: str) -> Tuple[Optional[str], bool]:
    """Returns (language_code or None if ambiguous, explicit_switch_request)."""
    text = (raw_text or "").strip()
    if not text:
        return None, False

    switch_code = _detect_switch_request(text)
    if switch_code:
        return switch_code, True

    if _count_script(text, "\u0900", "\u097f") >= 2:
        return "hi", False
    if _count_script(text, "\u0b80", "\u0bff") >= 2:
        return "ta", False
    if _count_script(text, "\u0c00", "\u0c7f") >= 2:
        return "te", False

    tokens = re.findall(r"[a-z']+", text.lower())
    if not tokens:
        return None, False
    token_set = set(tokens)
    if token_set & _TENGLISH_MARKERS:
        return "tenglish", False
    if token_set & _TANGLISH_MARKERS:
        return "tanglish", False
    if token_set & _HINGLISH_MARKERS:
        return "hinglish", False
    if all(t in _AMBIGUOUS for t in tokens):
        return None, False
    if len(tokens) >= 3:
        return "en", False
    return None, False


_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_TAMIL_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")

_KEYWORD_MAP = [
    # Telugu (longest phrases first)
    ("ఈరోజు", "ivvala"), ("ఎన్ని", "enni"), ("ఎంత", "entha"), ("ఫోన్", "phone"), ("ఎక్కడ", "ekkada"),
    ("ఎలా ఉన్నారు", "ela unnaru"), ("బాగున్నారా", "bagunnara"), ("నమస్కారం", "namaskaram"),
    ("ధన్యవాదాలు", "dhanyavadalu"), ("హార్డ్‌వేర్", "hardware"), ("హార్డ్వేర్", "hardware"),
    ("కృష్ణా", "krishna"), ("కృష్ణ", "krishna"), ("గణేష్", "ganesh"), ("భారత్", "bharat"),
    ("మురుగన్", "murugan"), ("బస్తాలు", "bags"), ("బస్తా", "bags"), ("సంచులు", "bags"),
    ("డెలివరీ", "deliver"), ("డబ్బులు", "cash"), ("డబ్బు", "cash"), ("క్యాష్", "cash"),
    ("రూపాయలు", "rupees"), ("వేలు", "thousand"), ("వెయ్యి", "thousand"), ("అవును", "avunu"),
    ("సరే", "sare"), ("వద్దు", "vaddu"), ("ప్రియా", "priya"), ("మేనేజర్", "manager"),
    ("బ్యాలెన్స్", "balance"), ("బాకీ", "baki"), ("చిరిగిన", "torn"), ("పాడైన", "damage"),
    ("పద్దెనిమిది", "18"), ("ఇరవై ఐదు", "25"), ("ఇరవై", "20"), ("పది", "10"),
    ("వచ్చాయి", "vachayi"), ("వచ్చింది", "vachindi"), ("ఇచ్చారు", "icharu"),
    ("బాగోలేదు", "bagoledu"), ("జ్వరం", "jwaram"), ("తలనొప్పి", "headache"), ("ఆరోగ్యం", "unwell"),
    ("చేయలేకపోయాను", "couldnt deliver"), ("చేయలేదు", "didnt deliver"), ("మూసి ఉంది", "shop closed"), ("వర్షం", "rain"),
    # Hindi phrases first (longest match first)
    ("तबीयत खराब", "tabiyat kharab"), ("तबीयत ठीक नहीं", "tabiyat kharab"), ("बीमार", "bimar"), ("बुखार", "bukhar"),
    ("नहीं कर पाया", "couldnt deliver"), ("नहीं हो पाई", "couldnt deliver"), ("दुकान बंद", "shop closed"), ("बारिश", "rain"),
    ("आज", "aaj"), ("कितनी", "kitni"), ("कितने", "kitne"), ("फ़ोन", "phone"), ("फोन", "phone"),
    ("नंबर", "number"), ("कहाँ", "kahan"), ("कहां", "kahan"),
    ("जी हाँ", "haan"), ("ठीक है", "theek hai"), ("कर दीजिए", "kar do"), ("कर दो", "kar do"),
    ("मिल गया", "mil gaya"), ("मिल गए", "mil gaya"), ("बात करा", "baat kar"), ("बात कर", "baat kar"),
    ("कैसे हो", "kaise ho"), ("कैसे हैं", "kaise ho"), ("क्या हाल", "kya haal"),
    ("क्या कर सकते", "kya kar sakte"), ("मत करो", "mat karo"),
    ("कृष्णा", "krishna"), ("कृष्ण", "krishna"), ("हार्डवेयर", "hardware"), ("गणेश", "ganesh"),
    ("भारत", "bharat"), ("ट्रेडर्स", "traders"), ("मुरुगन", "murugan"), ("बिल्डर्स", "builders"),
    ("स्टोर्स", "stores"), ("बैग्स", "bags"), ("बैग", "bags"), ("बोरियाँ", "bags"), ("बोरियां", "bags"),
    ("बोरी", "bags"), ("कट्टे", "bags"), ("डिलीवरी", "deliver"), ("डिलीवर", "deliver"),
    ("पहुँचा", "deliver"), ("पहुंचा", "deliver"), ("कैश", "cash"), ("नकद", "cash"),
    ("रुपये", "rupees"), ("रुपए", "rupees"), ("रूपये", "rupees"), ("मिला", "mila"), ("मिले", "mila"),
    ("फटी", "phate"), ("फटे", "phate"), ("फटा", "phata"), ("ख़राब", "kharab"), ("खराब", "kharab"),
    ("डैमेज", "damage"), ("टूटी", "torn"), ("डिस्काउंट", "discount"), ("छूट", "chhoot"),
    ("रुकिए", "ruko"), ("रुको", "ruko"), ("नहीं", "nahi"), ("नही", "nahi"), ("प्रिया", "priya"),
    ("मैनेजर", "manager"), ("गुस्सा", "gussa"), ("हाँ", "haan"), ("हां", "haan"), ("पोस्ट", "post"),
    ("धन्यवाद", "dhanyawad"), ("शुक्रिया", "shukriya"), ("नमस्ते", "namaste"), ("नमस्कार", "namaste"),
    ("हैलो", "hello"), ("हेलो", "hello"), ("बैलेंस", "balance"), ("बाकी", "baki"), ("कितना", "kitna"),
    ("इनवॉइस", "invoice"), ("पेंडिंग", "pending"), ("हिसाब", "hisaab"), ("नियम", "policy"),
    ("पॉलिसी", "policy"), ("मदद", "help"), ("हज़ार", "thousand"), ("हजार", "thousand"),
    ("पच्चीस", "25"), ("अठारह", "18"), ("पंद्रह", "15"), ("बीस", "20"), ("पाँच", "5"), ("पांच", "5"),
    ("दस", "10"), ("तीन", "3"), ("चार", "4"),
    # Tamil
    ("இன்னைக்கு", "innaikku"), ("இன்று", "innaikku"), ("எத்தனை", "ethana"), ("எவ்வளவு", "evvalavu"),
    ("போன்", "phone"), ("எங்க", "enga"), ("என்ன", "enna"),
    ("எப்படி இருக்கீங்க", "epdi irukeenga"), ("எப்படி இருக்கிங்க", "epdi irukeenga"),
    ("இறக்கிட்டேன்", "unload pannitten"), ("கிடைச்சுது", "kedaichu"), ("கிடைத்தது", "kedaichu"),
    ("முருகன்", "murugan"), ("கிருஷ்ணா", "krishna"), ("மூட்டைகள்", "bags"), ("மூட்டை", "bags"),
    ("பைகள்", "bags"), ("டெலிவரி", "deliver"), ("பணம்", "cash"), ("காசு", "cash"),
    ("ரூபாய்", "rupees"), ("ஆமா", "aama"), ("ஆம்", "aama"), ("சரி", "seri"), ("நன்றி", "nandri"),
    ("வணக்கம்", "vanakkam"), ("சேதம்", "damage"), ("கிழிஞ்ச", "torn"), ("ஆயிரம்", "thousand"),
    ("இருபத்தைந்து", "25"), ("பதினெட்டு", "18"), ("இருபது", "20"), ("மேனேஜர்", "manager"),
    ("பிரியா", "priya"), ("பாக்கி", "baki"), ("வேண்டாம்", "vendam"),
    ("உடம்பு சரியில்லை", "udambu sariyilla"), ("காய்ச்சல்", "kaichal"), ("கடை மூடி", "shop closed"), ("மழை", "rain"),
]


def normalize_for_parsing(text: str) -> str:
    """Romanizes key Hindi/Tamil field-ops keywords & numbers so NLU regexes work for any script."""
    out = (text or "").translate(_DEVANAGARI_DIGITS).translate(_TAMIL_DIGITS)
    for src, dst in _KEYWORD_MAP:
        out = out.replace(src, f" {dst} ")
    out = out.replace("₹", " rs ").replace("'", "").replace("’", "")
    out = out.lower().replace(",", "")
    # Romanized Telugu / Tamil field words -> canonical NLU tokens
    out = re.sub(r"\b(?:bastalu|basthalu|basta|bastha|sanchulu|moottai|mootai)\b", "bags", out)
    out = re.sub(r"\b(?:dabbulu|dabbu|panam|kaasu)\b", "cash", out)
    out = re.sub(r"\b(?:icharu|ichadu|ichindi|ichaaru|vachindi|vachayi)\b", "received", out)
    out = re.sub(r"\b(?:velu|veylu|vela|aayiram)\b", "thousand", out)
    out = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:thousand|hazaar|hazar|hajar)",
        lambda m: str(int(float(m.group(1)) * 1000)),
        out,
    )
    return re.sub(r"\s+", " ", out).strip()


TEMPLATES: Dict[str, Dict[str, str]] = {
    "greeting": {
        "en": "Hi Raju! DeliverEx Live here — which shop did you just deliver to?",
        "hinglish": "Namaste Raju bhai! DeliverEx Live AI sun raha hai — bataiye kis shop pe delivery hui, ya camera se damaged bags dikhaiye.",
        "hi": "नमस्ते राजू भाई! DeliverEx Live तैयार है — बताइए किस दुकान पर डिलीवरी हुई?",
        "tanglish": "Vanakkam anna! DeliverEx Live ready — endha kadaiyila delivery aachu nu sollunga.",
        "ta": "வணக்கம் அண்ணா! DeliverEx Live தயார் — எந்த கடையில டெலிவரி ஆச்சுன்னு சொல்லுங்க.",
    },
    "lang_switch": {
        "en": "Sure Raju, I'll speak English from now on. Which shop are we updating?",
        "hinglish": "Theek hai Raju bhai, ab Hinglish mein baat karte hain! Kaunsi shop ka update hai?",
        "hi": "ठीक है राजू भाई, अब मैं हिंदी में बात करूँगा! किस दुकान का अपडेट है?",
        "tanglish": "Seri anna, ini Tanglish-la pesuren! Endha kadai update pannanum?",
        "ta": "சரி அண்ணா, இனிமே தமிழ்லயே பேசுறேன்! எந்த கடை அப்டேட் பண்ணணும்?",
    },
    "unclear": {
        "en": "Sorry Raju, I didn't catch that clearly — could you say it again a bit closer to the mic?",
        "hinglish": "Maaf kijiye Raju bhai, aawaz clear nahi aayi — thoda paas bolke dubara boliye.",
        "hi": "माफ़ कीजिए राजू भाई, आवाज़ साफ़ नहीं आई — थोड़ा पास बोलकर दोबारा कहिए।",
        "tanglish": "Mannikkanum anna, sound clear-a illa — konjam pakkathula pesunga.",
        "ta": "மன்னிக்கணும் அண்ணா, சத்தம் தெளிவா இல்ல — கொஞ்சம் பக்கத்துல பேசுங்க.",
    },
    "lookup_confirm": {
        "en": "Got it, Raju. I found {name} (ID {cid}) with pending invoice {inv} — {exp} bags and Rs {due} due. Shall I post {deliv} bags and Rs {cash} cash to the Tally ledger?",
        "hinglish": "Ji Raju bhai, {name} (ID {cid}) ka pending invoice {inv} mil gaya — total {exp} bags aur Rs {due} due hai. Kya main {deliv} bags aur Rs {cash} cash Tally ledger mein post kar doon?",
        "hi": "जी राजू भाई, {name} का पेंडिंग इनवॉइस {inv} मिल गया — कुल {exp} बोरी और {due} रुपये बाकी हैं। क्या मैं {deliv} बोरी और {cash} रुपये कैश टैली में दर्ज कर दूँ?",
        "tanglish": "Seri anna, {name} (ID {cid}) pending invoice {inv} kedaichuduchu — mottham {exp} bags, Rs {due} balance irukku. {deliv} bags, Rs {cash} cash Tally-la post pannatuma?",
        "ta": "சரி அண்ணா, {name} நிலுவை இன்வாய்ஸ் {inv} கிடைச்சுது — மொத்தம் {exp} மூட்டை, {due} ரூபாய் பாக்கி இருக்கு. {deliv} மூட்டை, {cash} ரூபாய் பணத்தை Tally-ல பதிவு பண்ணட்டுமா?",
    },
    "confirm_done": {
        "en": "Done, Raju! {deliv} bags and Rs {cash} cash for {name} ({inv}) are synced to Tally ledger {tally}. Which shop is next?",
        "hinglish": "Done Raju bhai! {name} ({inv}) ke {deliv} bags aur Rs {cash} cash Tally ledger ({tally}) mein sync kar diye hain. Agli kaunsi shop pe jaana hai?",
        "hi": "हो गया राजू भाई! {name} ({inv}) की {deliv} बोरी और {cash} रुपये कैश टैली लेजर ({tally}) में दर्ज कर दिए हैं। अगली दुकान कौन सी है?",
        "tanglish": "Mudinjiduchu anna! {name} ({inv}) — {deliv} bags, Rs {cash} cash Tally ledger ({tally})-la sync pannitten. Adutha kadai enga?",
        "ta": "முடிஞ்சுது அண்ணா! {name} — {deliv} மூட்டை, {cash} ரூபாய் Tally லெட்ஜர்ல ({tally}) பதிவு பண்ணிட்டேன். அடுத்த கடை எது?",
    },
    "confirm_nothing": {
        "en": "I'm ready! Tell me which shop's delivery or cash you'd like to update.",
        "hinglish": "Ji, main ready hoon! Bataiye kaunsi shop ka delivery count ya cash Tally mein update karna hai?",
        "hi": "जी, मैं तैयार हूँ! बताइए किस दुकान की डिलीवरी या कैश अपडेट करना है?",
        "tanglish": "Seri anna, naan ready. Endha kadai delivery illa cash update pannanum nu sollunga.",
        "ta": "சரி அண்ணா, நான் தயார். எந்த கடை டெலிவரி அல்லது பணம் அப்டேட் பண்ணணும்னு சொல்லுங்க.",
    },
    "cancel": {
        "en": "No problem, I haven't posted anything. Tell me the correct bags and cash whenever you're ready.",
        "hinglish": "Koi baat nahi Raju bhai, maine kuch post nahi kiya. Sahi bags aur cash bata dijiye.",
        "hi": "कोई बात नहीं राजू भाई, मैंने कुछ दर्ज नहीं किया। सही बोरी और कैश बता दीजिए।",
        "tanglish": "Paravaillai anna, edhuvum post pannala. Correct bags, cash sollunga.",
        "ta": "பரவாயில்லை அண்ணா, எதுவும் பதிவு பண்ணல. சரியான மூட்டை, பணம் சொல்லுங்க.",
    },
    "how_are_you": {
        "en": "I'm doing great and listening live! Tell me which shop delivery or invoice update you'd like to log.",
        "hinglish": "Main bilkul badhiya hoon Raju bhai! Aap batao mandi mein kaam kaisa chal raha hai — kaunsi shop ki delivery update karni hai?",
        "hi": "मैं बिल्कुल बढ़िया हूँ राजू भाई! आप बताइए, मंडी में काम कैसा चल रहा है — किस दुकान का अपडेट करना है?",
        "tanglish": "Naan nalla irukken anna! Neenga epdi irukeenga? Endha kadai update pannanum?",
        "ta": "நான் நல்லா இருக்கேன் அண்ணா! நீங்க எப்படி இருக்கீங்க? எந்த கடை அப்டேட் பண்ணணும்?",
    },
    "help": {
        "en": "I can log bag deliveries and cash straight into Tally, verify torn-bag photos under SOP rules, escalate disputes to Area Manager Priya, and send WhatsApp receipts.",
        "hinglish": "Raju bhai, aap bas naturally bol sakte ho — main bags aur cash Tally mein post kar sakta hoon, camera se torn bags check karke Priya ma'am se 1-tap approval le sakta hoon, aur WhatsApp receipt bhej sakta hoon!",
        "hi": "राजू भाई, आप बस आराम से बोलिए — मैं बोरी और कैश टैली में दर्ज कर सकता हूँ, फटी बोरियों की फोटो जाँचकर प्रिया मैडम से मंज़ूरी ले सकता हूँ, और WhatsApp रसीद भेज सकता हूँ।",
        "tanglish": "Anna, neenga casual-a pesalaam — bags, cash Tally-la post pannuven, damaged bags photo check panni Priya madam approval vanguven, WhatsApp receipt anuppuven!",
        "ta": "அண்ணா, சாதாரணமா பேசுங்க — மூட்டை, பணம் Tally-ல பதிவு பண்ணுவேன், சேதமான மூட்டை போட்டோ சரிபார்த்து பிரியா மேடம் அனுமதி வாங்குவேன், WhatsApp ரசீது அனுப்புவேன்!",
    },
    "ack": {
        "en": "Anytime! Let me know whenever you're ready for the next shop update.",
        "hinglish": "Bilkul Raju bhai! Jab agli shop pe pahunchna ho bas bol dena, main line par hi hoon.",
        "hi": "बिल्कुल राजू भाई! अगली दुकान पर पहुँचकर बता दीजिए, मैं लाइन पर ही हूँ।",
        "tanglish": "Seri anna! Adutha kadaikku poyitu sollunga, naan line-la dhaan irukken.",
        "ta": "சரி அண்ணா! அடுத்த கடைக்கு போனதும் சொல்லுங்க, நான் லைன்லயே இருக்கேன்.",
    },
    "status": {
        "en": "So far Rs {total} cash is synced to Tally across {entries} entries, and {pending} approvals are pending with Priya.",
        "hinglish": "Raju bhai, abhi tak Rs {total} cash Tally mein sync hua hai ({entries} entries) aur {pending} approvals Priya ma'am ke paas pending hain.",
        "hi": "राजू भाई, अब तक {total} रुपये टैली में दर्ज हुए हैं ({entries} एंट्री), और {pending} मंज़ूरियाँ प्रिया मैडम के पास बाकी हैं।",
        "tanglish": "Anna, ippo varaikkum Rs {total} cash Tally-la sync aachu ({entries} entries), {pending} approvals Priya madam kitta pending.",
        "ta": "அண்ணா, இதுவரை {total} ரூபாய் Tally-ல பதிவாச்சு ({entries} பதிவுகள்), {pending} அனுமதிகள் பிரியா மேடம் கிட்ட நிலுவையில இருக்கு.",
    },
    "lookup_found": {
        "en": "{name} ({inv}) has {exp} bags and Rs {due} balance due.",
        "hinglish": "{name} ({inv}) par {exp} bags aur Rs {due} balance due hai.",
        "hi": "{name} ({inv}) पर {exp} बोरी और {due} रुपये बाकी हैं।",
        "tanglish": "{name} ({inv})-ku {exp} bags, Rs {due} balance pending irukku anna.",
        "ta": "{name} ({inv}) கடைக்கு {exp} மூட்டை, {due} ரூபாய் பாக்கி இருக்கு அண்ணா.",
    },
    "lookup_ask": {
        "en": "Which shop should I check — Krishna Hardware, Shri Ganesh Stores, Bharat Traders, or Murugan Builders?",
        "hinglish": "Raju bhai, kaunsi shop ka balance check karna hai — Krishna Hardware, Shri Ganesh Stores, Bharat Traders, ya Murugan Builders?",
        "hi": "राजू भाई, किस दुकान का बैलेंस देखना है — कृष्णा हार्डवेयर, श्री गणेश स्टोर्स, भारत ट्रेडर्स या मुरुगन बिल्डर्स?",
        "tanglish": "Anna, endha kadai balance paakanum — Krishna Hardware, Shri Ganesh Stores, Bharat Traders, illa Murugan Builders?",
        "ta": "அண்ணா, எந்த கடை பாக்கி பார்க்கணும் — Krishna Hardware, Shri Ganesh Stores, Bharat Traders, அல்லது Murugan Builders?",
    },
    "policy": {
        "en": "Per DeliverEx SOPs: {sops}. Drivers can auto-approve discounts only up to Rs 200 (SOP-4.2).",
        "hinglish": "DeliverEx SOP ke mutabik: {sops}. Driver auto-discount cap Rs 200 hai (SOP-4.2).",
        "hi": "DeliverEx नियमों के अनुसार: {sops}। ड्राइवर की छूट सीमा 200 रुपये है (SOP-4.2)।",
        "tanglish": "DeliverEx SOP padi: {sops}. Driver auto-discount limit Rs 200 dhaan (SOP-4.2), anna.",
        "ta": "DeliverEx விதிமுறைப்படி: {sops}. டிரைவர் தள்ளுபடி வரம்பு 200 ரூபாய் மட்டும் (SOP-4.2).",
    },
    "escalate": {
        "en": "Don't worry, Raju. Under SOP-6.0 I've sent Area Manager Priya a live call takeover alert ({hid}) with the full {shop} summary.",
        "hinglish": "Bilkul Raju bhai, chinta mat karo. SOP-6.0 ke tahat maine Area Manager Priya ma'am ko {shop} ki poori summary ke saath Live Call Takeover alert ({hid}) bhej diya hai.",
        "hi": "चिंता मत कीजिए राजू भाई। मैंने एरिया मैनेजर प्रिया मैडम को {shop} की पूरी जानकारी के साथ लाइव कॉल अलर्ट ({hid}) भेज दिया है।",
        "tanglish": "Kavalai padaadheenga anna. SOP-6.0 padi Area Manager Priya madam-ku {shop} full summary-oda Live Call Takeover alert ({hid}) anuppitten.",
        "ta": "கவலைப்படாதீங்க அண்ணா. ஏரியா மேனேஜர் பிரியா மேடத்துக்கு {shop} முழு விவரத்தோட அவசர அழைப்பு ({hid}) அனுப்பிட்டேன்.",
    },
    "damage": {
        "en": "Understood — {dmg} torn bags at {shop} are logged to quarantine (SOP-5.1), and approval card {aid} is with Priya.",
        "hinglish": "Samajh gaya Raju bhai — {shop} ke {dmg} torn bags quarantine mein log ho gaye hain (SOP-5.1) aur Priya ma'am ko approval card {aid} bhej diya hai.",
        "hi": "समझ गया राजू भाई — {shop} की {dmg} फटी बोरियाँ अलग दर्ज कर दी हैं (SOP-5.1) और प्रिया मैडम को मंज़ूरी कार्ड {aid} भेज दिया है।",
        "tanglish": "Purinjudhu anna — {shop}-la {dmg} damaged bags quarantine-la log pannitten (SOP-5.1), Priya madam-ku approval card {aid} anuppitten.",
        "ta": "புரிஞ்சுது அண்ணா — {shop}-ல {dmg} சேதமான மூட்டைகளை பதிவு பண்ணிட்டேன், பிரியா மேடத்துக்கு அனுமதி கார்டு {aid} அனுப்பிட்டேன்.",
    },
    "delivery_hitl_bargein": {
        "en": "Okay, correction noted — {deliv} bags delivered, {dmg} damaged bags quarantined, and Rs {cash} cash posted to Tally ({tally}). Per {policy}, I've sent Priya a 1-tap approval!",
        "hinglish": "Achha samajh gaya Raju bhai — {deliv} bags delivered, {dmg} damaged bags quarantine mein, aur Rs {cash} cash Tally ledger ({tally}) mein post kar diya hai. {policy} ke hisaab se Priya ma'am ko 1-tap approval bhej diya hai!",
        "hi": "अच्छा समझ गया राजू भाई — {deliv} बोरी डिलीवर, {dmg} फटी बोरियाँ अलग, और {cash} रुपये कैश टैली ({tally}) में दर्ज कर दिए। {policy} के हिसाब से प्रिया मैडम को मंज़ूरी भेज दी है!",
        "tanglish": "Seri anna, purinjudhu — {deliv} bags delivered, {dmg} damaged bags quarantine-la, Rs {cash} cash Tally ledger ({tally})-la post pannitten. {policy} padi Priya madam-ku 1-tap approval anuppitten!",
        "ta": "சரி அண்ணா, புரிஞ்சுது — {deliv} மூட்டை டெலிவரி, {dmg} சேதமான மூட்டை தனியா வைச்சாச்சு, {cash} ரூபாய் Tally-ல ({tally}) பதிவாச்சு. {policy} படி பிரியா மேடத்துக்கு அனுமதி அனுப்பிட்டேன்!",
    },
    "delivery_hitl": {
        "en": "Noted — {deliv} bags and Rs {cash} cash for {shop} ({inv}) are logged in Tally. The exception ({policy}) is with Priya for 1-tap approval.",
        "hinglish": "Noted Raju bhai — {shop} ({inv}) ke {deliv} bags aur Rs {cash} cash Tally mein log ho gaye. Exception ({policy}) Priya ma'am ke 1-tap approval ke liye bhej diya hai.",
        "hi": "दर्ज कर लिया राजू भाई — {shop} ({inv}) की {deliv} बोरी और {cash} रुपये टैली में दर्ज हो गए। अपवाद ({policy}) प्रिया मैडम की मंज़ूरी के लिए भेज दिया है।",
        "tanglish": "Note pannitten anna — {shop} ({inv}) {deliv} bags, Rs {cash} cash Tally-la log aachu. Exception ({policy}) Priya madam approval-ku anuppitten.",
        "ta": "பதிவு பண்ணிட்டேன் அண்ணா — {shop} ({inv}) {deliv} மூட்டை, {cash} ரூபாய் Tally-ல பதிவாச்சு. விதிவிலக்கு ({policy}) பிரியா மேடம் அனுமதிக்கு அனுப்பியாச்சு.",
    },
    "delivery_ok": {
        "en": "Great job, Raju! {deliv} bags and Rs {cash} cash for {shop} ({inv}) are synced to Tally, and the WhatsApp receipt is sent!",
        "hinglish": "Badhiya Raju bhai! {shop} ({inv}) ke {deliv} bags aur Rs {cash} cash Tally mein sync ho gaya hai. Official WhatsApp receipt bhej di gayi hai!",
        "hi": "बढ़िया राजू भाई! {shop} ({inv}) की {deliv} बोरी और {cash} रुपये कैश टैली में दर्ज हो गए। WhatsApp रसीद भेज दी गई है!",
        "tanglish": "Super anna! {shop} invoice {inv} full settle aayiduchu — {deliv} bags intact, Rs {cash} cash Tally ledger-la update pannitten, official WhatsApp receipt-um anuppitten!",
        "ta": "சூப்பர் அண்ணா! {shop} இன்வாய்ஸ் {inv} முழுசா செட்டில் ஆச்சு — {deliv} மூட்டை, {cash} ரூபாய் Tally-ல பதிவு பண்ணிட்டேன், WhatsApp ரசீதும் அனுப்பிட்டேன்!",
    },
}


_TELUGU_TEMPLATES: Dict[str, Dict[str, str]] = {
    "greeting": {
        "tenglish": "Namaskaram anna! DeliverEx Live ready — e shop lo delivery ayyindo cheppandi.",
        "te": "నమస్కారం అన్నా! DeliverEx Live సిద్ధంగా ఉంది — ఏ షాప్‌లో డెలివరీ అయిందో చెప్పండి.",
    },
    "lang_switch": {
        "tenglish": "Sare anna, ika nunchi Tenglish lo matladatanu! E shop update cheyyali?",
        "te": "సరే అన్నా, ఇక నుంచి తెలుగులోనే మాట్లాడతాను! ఏ షాప్ అప్‌డేట్ చేయాలి?",
    },
    "unclear": {
        "tenglish": "Sorry anna, sound clear ga raledu — konchem daggaraga matladandi.",
        "te": "క్షమించండి అన్నా, మాట స్పష్టంగా వినిపించలేదు — కొంచెం దగ్గరగా మాట్లాడండి.",
    },
    "lookup_confirm": {
        "tenglish": "Sare anna, {name} (ID {cid}) pending invoice {inv} dorikindi — motham {exp} bags, Rs {due} baaki undi. {deliv} bags, Rs {cash} cash Tally lo post cheyyana?",
        "te": "సరే అన్నా, {name} పెండింగ్ ఇన్వాయిస్ {inv} దొరికింది — మొత్తం {exp} బస్తాలు, {due} రూపాయలు బాకీ ఉంది. {deliv} బస్తాలు, {cash} రూపాయలు Tally లో నమోదు చేయనా?",
    },
    "confirm_done": {
        "tenglish": "Ayipoyindi anna! {name} ({inv}) — {deliv} bags, Rs {cash} cash Tally ledger ({tally}) lo sync chesanu. Next shop edi?",
        "te": "అయిపోయింది అన్నా! {name} ({inv}) — {deliv} బస్తాలు, {cash} రూపాయలు Tally లెడ్జర్ ({tally}) లో నమోదు చేశాను. తర్వాత షాప్ ఏది?",
    },
    "confirm_nothing": {
        "tenglish": "Sare anna, nenu ready. E shop delivery leda cash update cheyyalo cheppandi.",
        "te": "సరే అన్నా, నేను సిద్ధం. ఏ షాప్ డెలివరీ లేదా డబ్బు అప్‌డేట్ చేయాలో చెప్పండి.",
    },
    "cancel": {
        "tenglish": "Parledu anna, emi post cheyyaledu. Correct bags, cash cheppandi.",
        "te": "పర్వాలేదు అన్నా, ఏమీ నమోదు చేయలేదు. సరైన బస్తాలు, డబ్బు చెప్పండి.",
    },
    "how_are_you": {
        "tenglish": "Nenu bagunnanu anna! Meeru ela unnaru? E shop update cheyyali?",
        "te": "నేను బాగున్నాను అన్నా! మీరు ఎలా ఉన్నారు? ఏ షాప్ అప్‌డేట్ చేయాలి?",
    },
    "help": {
        "tenglish": "Anna, casual ga matladandi — bags, cash Tally lo post chestanu, damaged bags photo check chesi Priya madam approval teesukuntanu, WhatsApp receipt pamputanu!",
        "te": "అన్నా, మామూలుగా మాట్లాడండి — బస్తాలు, డబ్బు Tally లో నమోదు చేస్తాను, పాడైన బస్తాల ఫోటో చూసి ప్రియా మేడం అనుమతి తీసుకుంటాను, WhatsApp రసీదు పంపుతాను!",
    },
    "ack": {
        "tenglish": "Sare anna! Next shop ki vellaka cheppandi, nenu line lone unnanu.",
        "te": "సరే అన్నా! తర్వాత షాప్‌కి వెళ్ళాక చెప్పండి, నేను లైన్‌లోనే ఉన్నాను.",
    },
    "status": {
        "tenglish": "Anna, ippati varaku Rs {total} cash Tally lo sync ayyindi ({entries} entries), {pending} approvals Priya madam daggara pending lo unnayi.",
        "te": "అన్నా, ఇప్పటివరకు {total} రూపాయలు Tally లో నమోదయ్యాయి ({entries} ఎంట్రీలు), {pending} అనుమతులు ప్రియా మేడం దగ్గర పెండింగ్‌లో ఉన్నాయి.",
    },
    "lookup_found": {
        "tenglish": "{name} ({inv}) ki {exp} bags, Rs {due} baaki undi anna.",
        "te": "{name} ({inv}) కి {exp} బస్తాలు, {due} రూపాయలు బాకీ ఉంది అన్నా.",
    },
    "lookup_ask": {
        "tenglish": "Anna, e shop balance chudali — Krishna Hardware, Shri Ganesh Stores, Bharat Traders, leda Murugan Builders?",
        "te": "అన్నా, ఏ షాప్ బాకీ చూడాలి — Krishna Hardware, Shri Ganesh Stores, Bharat Traders, లేదా Murugan Builders?",
    },
    "policy": {
        "tenglish": "DeliverEx SOP prakaram: {sops}. Driver auto-discount limit Rs 200 matrame (SOP-4.2), anna.",
        "te": "DeliverEx నియమాల ప్రకారం: {sops}. డ్రైవర్ డిస్కౌంట్ పరిమితి 200 రూపాయలు మాత్రమే (SOP-4.2).",
    },
    "escalate": {
        "tenglish": "Tension padakandi anna. SOP-6.0 prakaram Area Manager Priya madam ki {shop} full summary tho Live Call Takeover alert ({hid}) pampanu.",
        "te": "కంగారు పడకండి అన్నా. ఏరియా మేనేజర్ ప్రియా మేడంకి {shop} పూర్తి వివరాలతో లైవ్ కాల్ అలర్ట్ ({hid}) పంపాను.",
    },
    "damage": {
        "tenglish": "Ardham ayyindi anna — {shop} lo {dmg} damaged bags quarantine lo log chesanu (SOP-5.1), Priya madam ki approval card {aid} pampanu.",
        "te": "అర్థమైంది అన్నా — {shop} లో {dmg} పాడైన బస్తాలను నమోదు చేశాను (SOP-5.1), ప్రియా మేడంకి అనుమతి కార్డు {aid} పంపాను.",
    },
    "delivery_hitl_bargein": {
        "tenglish": "Sare anna, ardham ayyindi — {deliv} bags delivered, {dmg} damaged bags quarantine lo, Rs {cash} cash Tally ledger ({tally}) lo post chesanu. {policy} prakaram Priya madam ki 1-tap approval pampanu!",
        "te": "సరే అన్నా, అర్థమైంది — {deliv} బస్తాలు డెలివరీ, {dmg} పాడైన బస్తాలు వేరుగా, {cash} రూపాయలు Tally ({tally}) లో నమోదు చేశాను. {policy} ప్రకారం ప్రియా మేడంకి అనుమతి పంపాను!",
    },
    "delivery_hitl": {
        "tenglish": "Note chesanu anna — {shop} ({inv}) {deliv} bags, Rs {cash} cash Tally lo log ayyindi. Exception ({policy}) Priya madam approval ki pampanu.",
        "te": "నమోదు చేశాను అన్నా — {shop} ({inv}) {deliv} బస్తాలు, {cash} రూపాయలు Tally లో నమోదయ్యాయి. మినహాయింపు ({policy}) ప్రియా మేడం అనుమతికి పంపాను.",
    },
    "delivery_ok": {
        "tenglish": "Super anna! {shop} ({inv}) — {deliv} bags, Rs {cash} cash Tally lo sync ayyindi, WhatsApp receipt kuda pampanu!",
        "te": "సూపర్ అన్నా! {shop} ({inv}) — {deliv} బస్తాలు, {cash} రూపాయలు Tally లో నమోదయ్యాయి, WhatsApp రసీదు కూడా పంపాను!",
    },
}
_INFO_TEMPLATES: Dict[str, Dict[str, str]] = {
    "ask_details": {
        "en": "Sure — for {shop}, how many bags were delivered and how much cash did you collect?",
        "hinglish": "Zaroor Raju bhai — {shop} pe kitne bags deliver hue aur kitna cash mila?",
        "hi": "ज़रूर राजू भाई — {shop} पर कितनी बोरी डिलीवर हुईं और कितना कैश मिला?",
        "tanglish": "Seri anna — {shop}-la evvalavu bags deliver aachu, evvalavu cash kedaichudhu?",
        "ta": "சரி அண்ணா — {shop}-ல எத்தனை மூட்டை டெலிவரி ஆச்சு, எவ்வளவு பணம் கிடைச்சுது?",
        "tenglish": "Sare anna — {shop} lo enni bags delivery ayyayi, entha cash vachindi?",
        "te": "సరే అన్నా — {shop} లో ఎన్ని బస్తాలు డెలివరీ అయ్యాయి, ఎంత డబ్బు వచ్చింది?",
    },
    "deliveries_today": {
        "en": "Today {count} deliveries are logged — {bags} bags in total and Rs {cash} cash collected, across {shops}.",
        "hinglish": "Aaj {count} deliveries log hui hain — total {bags} bags aur Rs {cash} cash, shops: {shops}.",
        "hi": "आज {count} डिलीवरी दर्ज हुई हैं — कुल {bags} बोरी और {cash} रुपये कैश, दुकानें: {shops}।",
        "tanglish": "Innaikku {count} deliveries log aachu — mottham {bags} bags, Rs {cash} cash, kadaigal: {shops}.",
        "ta": "இன்னைக்கு {count} டெலிவரி பதிவாச்சு — மொத்தம் {bags} மூட்டை, {cash} ரூபாய், கடைகள்: {shops}.",
        "tenglish": "Ivvala {count} deliveries log ayyayi — motham {bags} bags, Rs {cash} cash, shops: {shops}.",
        "te": "ఈరోజు {count} డెలివరీలు నమోదయ్యాయి — మొత్తం {bags} బస్తాలు, {cash} రూపాయలు, షాపులు: {shops}.",
    },
    "deliveries_none": {
        "en": "No deliveries are logged yet today. Tell me your first shop update!",
        "hinglish": "Aaj abhi tak koi delivery log nahi hui. Pehli shop ka update bataiye!",
        "hi": "आज अभी तक कोई डिलीवरी दर्ज नहीं हुई। पहली दुकान का अपडेट बताइए!",
        "tanglish": "Innaikku innum delivery edhuvum log aagala. Mudhal kadai update sollunga!",
        "ta": "இன்னைக்கு இன்னும் எந்த டெலிவரியும் பதிவாகல. முதல் கடை அப்டேட் சொல்லுங்க!",
        "tenglish": "Ivvala inka emi deliveries log kaledu. First shop update cheppandi!",
        "te": "ఈరోజు ఇంకా ఏ డెలివరీ నమోదు కాలేదు. మొదటి షాప్ అప్‌డేట్ చెప్పండి!",
    },
    "pending_list": {
        "en": "Pending balances: {items}. Total due is Rs {total}.",
        "hinglish": "Pending balance: {items}. Total Rs {total} due hai.",
        "hi": "बाकी बैलेंस: {items}। कुल {total} रुपये बाकी हैं।",
        "tanglish": "Pending balance: {items}. Mottham Rs {total} baaki irukku.",
        "ta": "நிலுவை பாக்கி: {items}. மொத்தம் {total} ரூபாய் பாக்கி.",
        "tenglish": "Pending balance: {items}. Motham Rs {total} baaki undi.",
        "te": "బాకీ వివరాలు: {items}. మొత్తం {total} రూపాయలు బాకీ.",
    },
    "contact": {
        "en": "{name} is at {location} on {route}. Phone: {phone}. Invoice {inv} has Rs {due} due.",
        "hinglish": "{name} {location} mein hai ({route}). Phone: {phone}. Invoice {inv} par Rs {due} baki hai.",
        "hi": "{name} {location} में है ({route})। फ़ोन: {phone}। इनवॉइस {inv} पर {due} रुपये बाकी हैं।",
        "tanglish": "{name} {location}-la irukku ({route}). Phone: {phone}. Invoice {inv}-ku Rs {due} baaki.",
        "ta": "{name} {location}-ல இருக்கு ({route}). போன்: {phone}. இன்வாய்ஸ் {inv}-க்கு {due} ரூபாய் பாக்கி.",
        "tenglish": "{name} {location} lo undi ({route}). Phone: {phone}. Invoice {inv} ki Rs {due} baaki undi.",
        "te": "{name} {location} లో ఉంది ({route}). ఫోన్: {phone}. ఇన్వాయిస్ {inv} కి {due} రూపాయలు బాకీ.",
    },
    "driver_unwell": {
        "en": "I'm sorry to hear you're not feeling well, Raju — please take rest first! I've alerted Area Manager Priya ({hid}) to arrange a backup driver and reschedule your remaining deliveries. Take care!",
        "hinglish": "Are Raju bhai, koi baat nahi — pehle apni tabiyat ka khayal rakho aur aaram karo! Maine Area Manager Priya ma'am ko alert ({hid}) bhej diya hai taaki backup driver arrange karke baaki deliveries reschedule kar dein.",
        "hi": "राजू भाई, कोई बात नहीं — पहले अपनी तबीयत का ख्याल रखिए और आराम कीजिए! मैंने एरिया मैनेजर प्रिया मैडम को अलर्ट ({hid}) भेज दिया है ताकि वे दूसरा ड्राइवर भेजकर बाकी डिलीवरी करा सकें।",
        "tanglish": "Udambu paathukonga anna, modhalla nalla rest edunga! Area Manager Priya madam-ku alert ({hid}) anuppitten, backup driver arrange panni meedhi deliveries reschedule panniduvaanga.",
        "ta": "உடம்பை பார்த்துக்கோங்க அண்ணா, முதல்ல நல்லா ஓய்வு எடுங்க! ஏரியா மேனேஜர் பிரியா மேடத்துக்கு தகவல் ({hid}) அனுப்பிட்டேன், வேற டிரைவர் ஏற்பாடு பண்ணி மீதி டெலிவரிகளை மாத்திடுவாங்க.",
        "tenglish": "Health jagratta anna, mundu rest teesukondi! Area Manager Priya madam ki alert ({hid}) pampanu, backup driver arrange chesi migatha deliveries reschedule chestaru.",
        "te": "మీ ఆరోగ్యం జాగ్రత్త అన్నా, ముందు మీరు విశ్రాంతి తీసుకోండి! ఏరియా మేనేజర్ ప్రియా మేడంకి సమాచారం ({hid}) పంపాను, వేరే డ్రైవర్‌ను ఏర్పాటు చేసి మిగతా డెలివరీలు పూర్తి చేయిస్తారు.",
    },
    "unable_to_deliver": {
        "en": "Understood, Raju — I have NOT logged any bags for {shop} (0 delivered). Should I notify Area Manager Priya to reschedule this delivery for you?",
        "hinglish": "Samajh gaya Raju bhai — {shop} par koi delivery post nahi ki hai (0 bags). Kya main Priya ma'am ko alert bhej doon taaki delivery reschedule ho sake?",
        "hi": "समझ गया राजू भाई — {shop} पर कोई डिलीवरी दर्ज नहीं की है। क्या मैं प्रिया मैडम को बता दूँ ताकि डिलीवरी दोबारा शेड्यूल हो सके?",
        "tanglish": "Purinjudhu anna — {shop}-la endha delivery-um log pannala (0 bags). Priya madam-ku sollittu delivery reschedule pannatuma?",
        "ta": "புரிஞ்சுது அண்ணா — {shop}-ல எந்த டெலிவரியும் பதிவு பண்ணல. பிரியா மேடத்துக்கு சொல்லி டெலிவரியை மாத்தி வைக்கட்டுமா?",
        "tenglish": "Ardham ayyindi anna — {shop} lo emi delivery log cheyyaledu (0 bags). Priya madam ki cheppi delivery reschedule cheyyana?",
        "te": "అర్థమైంది అన్నా — {shop} లో ఏ డెలివరీ నమోదు చేయలేదు. ప్రియా మేడంకి చెప్పి డెలివరీని మళ్ళీ షెడ్యూల్ చేయించనా?",
    },
    "shop_closed": {
        "en": "Got it — {shop} is closed, so 0 bags logged. Should I notify Area Manager Priya to reschedule this stop and message the shop owner?",
        "hinglish": "Noted Raju bhai — {shop} band hai, koi delivery log nahi ki. Kya main Priya ma'am ko update bhej doon taaki yeh stop reschedule ho jaye?",
        "hi": "नोट कर लिया राजू भाई — {shop} बंद है, कोई डिलीवरी दर्ज नहीं की। क्या मैं प्रिया मैडम को बता दूँ ताकि यह डिलीवरी दोबारा शेड्यूल हो सके?",
        "tanglish": "Note pannitten anna — {shop} moodi irukku, delivery log pannala. Priya madam-ku update panni reschedule pannatuma?",
        "ta": "குறிச்சிக்கிட்டேன் அண்ணா — {shop} மூடியிருக்கு, பதிவு பண்ணல. பிரியா மேடத்துக்கு சொல்லி மறுபடியும் ஏற்பாடு பண்ணட்டுமா?",
        "tenglish": "Note chesanu anna — {shop} close lo undi, emi log cheyyaledu. Priya madam ki update chesi reschedule cheyyana?",
        "te": "నమోదు చేసుకున్నాను అన్నా — {shop} మూసి ఉంది, ఏమీ పోస్ట్ చేయలేదు. ప్రియా మేడంకి చెప్పి మళ్ళీ షెడ్యూల్ చేయించనా?",
    },
    "delivery_delay": {
        "en": "No worries, Raju — drive safely first! Should I alert Area Manager Priya and let {shop} know you're delayed?",
        "hinglish": "Koi baat nahi Raju bhai, dhyan se chalaiye! Kya main Priya ma'am ko delay update bhej doon aur {shop} ko inform kar doon?",
        "hi": "कोई बात नहीं राजू भाई, संभलकर चलिए! क्या मैं प्रिया मैडम को देरी की सूचना भेज दूँ और {shop} को बता दूँ?",
        "tanglish": "Paravaillai anna, safe-a drive pannunga! Priya madam-ku delay update anuppi {shop}-ku sollidattuma?",
        "ta": "பரவாயில்லை அண்ணா, பாதுகாப்பா ஓட்டுங்க! பிரியா மேடத்துக்கும் {shop}-க்கும் தாமதம் பத்தி தகவல் அனுப்பட்டும்மா?",
        "tenglish": "Parledu anna, jagratta ga drive cheyyandi! Priya madam ki delay update pampi {shop} ki cheppana?",
        "te": "పర్వాలేదు అన్నా, జాగ్రత్తగా నడపండి! ప్రియా మేడంకి మరియు {shop} కి ఆలస్యం గురించి సమాచారం పంపనా?",
    },
    "handoff_confirmed": {
        "en": "Done, Raju! I've sent the reschedule & relief update ({hid}) for {shop} to Area Manager Priya Sharma.",
        "hinglish": "Ho gaya Raju bhai! Maine Area Manager Priya ma'am ko {shop} ka reschedule alert ({hid}) bhej diya hai.",
        "hi": "हो गया राजू भाई! मैंने एरिया मैनेजर प्रिया मैडम को {shop} का अपडेट ({hid}) भेज दिया है।",
        "tanglish": "Mudinjiduchu anna! Area Manager Priya madam-ku {shop} reschedule alert ({hid}) anuppitten.",
        "ta": "முடிஞ்சுது அண்ணா! ஏரியா மேனேஜர் பிரியா மேடத்துக்கு {shop} தகவல் ({hid}) அனுப்பிட்டேன்.",
        "tenglish": "Ayipoyindi anna! Area Manager Priya madam ki {shop} reschedule alert ({hid}) pampanu.",
        "te": "అయిపోయింది అన్నా! ఏరియా మేనేజర్ ప్రియా మేడంకి {shop} సమాచారం ({hid}) పంపాను.",
    },
    "not_understood": {
        "en": "I didn't quite get that. You can say things like 'Krishna Hardware 20 bags delivered, 15000 cash', 'what is pending?', or 'today's deliveries'.",
        "hinglish": "Samjha nahi Raju bhai. Aise boliye — 'Krishna Hardware pe 20 bags deliver, 15000 cash mila', 'kya pending hai?', ya 'aaj ki deliveries'.",
        "hi": "समझ नहीं आया राजू भाई। ऐसे बोलिए — 'कृष्णा हार्डवेयर पर 20 बोरी डिलीवर, 15000 कैश मिला', 'क्या बाकी है?', या 'आज की डिलीवरी'।",
        "tanglish": "Puriyala anna. Ippadi sollunga — 'Krishna Hardware 20 bags deliver, 15000 cash kedaichu', 'enna pending?', illa 'innaikku deliveries'.",
        "ta": "புரியல அண்ணா. இப்படி சொல்லுங்க — 'Krishna Hardware 20 மூட்டை டெலிவரி, 15000 பணம் கிடைச்சுது', 'என்ன பாக்கி இருக்கு?', அல்லது 'இன்னைக்கு டெலிவரி'.",
        "tenglish": "Ardham kaledu anna. Ila cheppandi — 'Krishna Hardware ki 20 bags delivery, 15000 cash vachindi', 'emi pending undi?', leda 'ivvala deliveries'.",
        "te": "అర్థం కాలేదు అన్నా. ఇలా చెప్పండి — 'Krishna Hardware కి 20 బస్తాలు డెలివరీ, 15000 డబ్బు వచ్చింది', 'ఏమి బాకీ ఉంది?', లేదా 'ఈరోజు డెలివరీలు'.",
    },
}
TEMPLATES.update(_INFO_TEMPLATES)

for _key, _variants in _TELUGU_TEMPLATES.items():
    TEMPLATES[_key].update(_variants)


def say(key: str, lang: str, **kwargs: Any) -> str:
    variants = TEMPLATES[key]
    template = variants.get(lang) or variants.get(DEFAULT_LANG) or next(iter(variants.values()))
    return template.format(**kwargs)
