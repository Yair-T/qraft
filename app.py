"""מחולל קודי QR בעברית — הפעלה: streamlit run app.py"""

from __future__ import annotations

import base64
import html
import io
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import quote, quote_plus

import qrcode
import streamlit as st
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


st.set_page_config(page_title="מחולל קודי QR", page_icon="▦", layout="wide")

ERROR_LEVELS = {"L — נמוך": ERROR_CORRECT_L, "M — בינוני": ERROR_CORRECT_M,
                "Q — גבוה": ERROR_CORRECT_Q, "H — הגבוה ביותר": ERROR_CORRECT_H}
CONTENT_TYPES = ["קישור", "טקסט", "דואר אלקטרוני", "שיחת טלפון", "SMS", "WhatsApp", "רשת Wi-Fi", "כרטיס ביקור (vCard)", "אירוע", "רשת חברתית", "PDF", "תמונה / וידאו"]


def init_state() -> None:
    defaults = {"kind": CONTENT_TYPES[0], "size": 400, "fg": "#14213D", "bg": "#FFFFFF",
                "ec": "M — בינוני", "border": 4, "round_logo": True, "history": []}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def rtl() -> None:
    st.markdown("""<style>
    :root{--ink:#17213b;--muted:#707789;--blue:#4d56df;--line:#e8eaf1;}
    html,body,[data-testid="stAppViewContainer"]{direction:rtl!important;background:#fafbfe;color:var(--ink);}
    [data-testid="stSidebar"]{display:none!important}
    .block-container{max-width:780px!important;padding:30px 24px 64px!important;margin:0 auto!important;}
    [data-testid="stMainBlockContainer"]{direction:rtl;text-align:center}
    .brand{display:flex;justify-content:center;align-items:center;gap:14px;margin:8px auto 4px;color:#101b3c;font-size:48px;font-weight:800;letter-spacing:-1.6px}
    .brand-icon{font-size:42px;color:#4d56df}.tagline{color:#73798a;font-size:17px;text-align:center;margin-bottom:30px}
    .hero{text-align:center;margin:20px 0 24px}.hero h1{font-size:30px;color:#121d3b;margin-bottom:8px}.muted{color:var(--muted)}
    .section-title{text-align:right;font-weight:750;font-size:19px;margin:0 0 12px;color:#17213b}
    div[data-testid="stVerticalBlockBorderWrapper"]{background:white;border:1px solid var(--line);border-radius:16px;padding:18px 22px;box-shadow:0 5px 22px #17213b08;margin:12px auto 18px}
    div[data-testid="stHorizontalBlock"]{justify-content:center;gap:10px}
    [data-testid="stButton"] button{border-radius:12px;border:1px solid #e4e7ef;background:#fff;color:#28314a;font-weight:600;min-height:56px;transition:.16s}
    [data-testid="stButton"] button:hover{border-color:#5864ec;color:#4652d8;background:#f5f6ff}
    [data-testid="stDownloadButton"] button{width:100%;border-radius:11px;background:#fff;border:1px solid #5964e8;color:#4652d8;font-weight:700;min-height:48px}
    [data-testid="stImage"]{text-align:center}[data-testid="stImage"] img{max-height:340px;object-fit:contain;background:white;border-radius:12px}
    [data-testid="stWidgetLabel"]{text-align:right}
    input,textarea,[data-baseweb="select"]{direction:rtl;text-align:right}
    [data-testid="stRadio"] label{justify-content:center}
    @media(max-width:640px){.block-container{padding:16px 12px 40px!important}.brand{font-size:38px}.hero h1{font-size:25px}}
    </style>""", unsafe_allow_html=True)


def clean_lines(*parts: str) -> str:
    return "\n".join(str(x).strip() for x in parts if str(x).strip())


def content_form(kind: str) -> str:
    """Draw fields for selected payload type and return standards-based QR payload."""
    if kind in ("קישור", "PDF", "תמונה / וידאו"):
        label = "כתובת URL או קישור לקובץ" if kind != "קישור" else "כתובת אתר"
        value = st.text_input(label, placeholder="https://example.com")
        if value.strip() and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value.strip()):
            value = "https://" + value.strip()
        return value.strip()
    if kind == "קישור (ישן)":
        value = st.text_input("כתובת URL", placeholder="https://example.com")
        if value.strip() and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value.strip()):
            value = "https://" + value.strip()
        return value.strip()
    if kind == "טקסט":
        return st.text_area("הטקסט לקידוד", height=140).strip()
    if kind == "דואר אלקטרוני":
        email = st.text_input("כתובת דוא״ל", placeholder="name@example.com")
        subject = st.text_input("נושא (אופציונלי)")
        body = st.text_area("גוף ההודעה (אופציונלי)", height=90)
        if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
            st.warning("כתובת הדוא״ל אינה תקינה.")
            return ""
        return f"mailto:{email.strip()}?subject={quote(subject)}&body={quote(body)}" if email.strip() else ""
    if kind == "שיחת טלפון":
        phone = st.text_input("מספר טלפון", placeholder="+972501234567")
        return f"tel:{phone.strip()}" if phone.strip() else ""
    if kind == "SMS":
        phone = st.text_input("מספר טלפון")
        message = st.text_area("הודעה (אופציונלי)", height=100)
        return f"SMSTO:{phone.strip()}:{message}" if phone.strip() else ""
    if kind == "WhatsApp":
        phone = st.text_input("מספר WhatsApp כולל קידומת מדינה", placeholder="972501234567")
        message = st.text_area("הודעה מוכנה מראש (אופציונלי)", height=90)
        digits = re.sub(r"\D", "", phone)
        return f"https://wa.me/{digits}" + (f"?text={quote_plus(message)}" if message else "") if digits else ""
    if kind == "רשת Wi-Fi":
        ssid = st.text_input("שם הרשת (SSID)")
        password = st.text_input("סיסמה", type="password")
        encryption = st.selectbox("הצפנה", ["WPA", "WEP", "ללא"])
        hidden = st.checkbox("רשת מוסתרת")
        esc = lambda s: s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace(":", "\\:").replace('"', '\\"')
        auth = "nopass" if encryption == "ללא" else encryption
        return f'WIFI:T:{auth};S:{esc(ssid)};P:{esc(password) if encryption != "ללא" else ""};H:{str(hidden).lower()};;' if ssid.strip() else ""
    if kind == "כרטיס ביקור (vCard)":
        name = st.text_input("שם מלא")
        phone = st.text_input("טלפון")
        email = st.text_input("דוא״ל")
        org = st.text_input("ארגון")
        website = st.text_input("אתר")
        if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
            st.warning("כתובת הדוא״ל אינה תקינה.")
            return ""
        entries = ["BEGIN:VCARD", "VERSION:3.0"]
        if name.strip(): entries += [f"FN:{name.strip()}", f"N:{name.strip()};;;;"]
        if phone.strip(): entries.append(f"TEL;TYPE=CELL:{phone.strip()}")
        if email.strip(): entries.append(f"EMAIL:{email.strip()}")
        if org.strip(): entries.append(f"ORG:{org.strip()}")
        if website.strip(): entries.append(f"URL:{website.strip()}")
        entries.append("END:VCARD")
        return "\r\n".join(entries) if name.strip() else ""
    if kind == "אירוע":
        title = st.text_input("כותרת האירוע")
        location = st.text_input("מיקום")
        today = date.today()
        start_day = st.date_input("תאריך התחלה", value=today)
        start_time = st.time_input("שעת התחלה", value=time(9, 0))
        end_day = st.date_input("תאריך סיום", value=today)
        end_time = st.time_input("שעת סיום", value=time(10, 0))
        description = st.text_area("תיאור", height=80)
        start = datetime.combine(start_day, start_time)
        end = datetime.combine(end_day, end_time)
        if end <= start:
            st.warning("מועד הסיום חייב להיות אחרי מועד ההתחלה.")
            return ""
        def stamp(d: datetime) -> str: return d.strftime("%Y%m%dT%H%M%S")
        return "\r\n".join(["BEGIN:VEVENT", f"SUMMARY:{title.strip()}", f"LOCATION:{location.strip()}",
                              f"DTSTART:{stamp(start)}", f"DTEND:{stamp(end)}", f"DESCRIPTION:{description.strip()}", "END:VEVENT"]) if title.strip() else ""
    platform = st.selectbox("פלטפורמה", ["Instagram", "Facebook", "TikTok", "LinkedIn", "YouTube", "X", "אחר"])
    profile = st.text_input("שם משתמש או קישור לפרופיל")
    if not profile.strip(): return ""
    if re.match(r"^https?://", profile.strip(), re.I): return profile.strip()
    handles = {"Instagram": "https://instagram.com/", "Facebook": "https://facebook.com/",
               "TikTok": "https://tiktok.com/@", "LinkedIn": "https://linkedin.com/in/",
               "YouTube": "https://youtube.com/@", "X": "https://x.com/"}
    return handles.get(platform, "") + profile.strip().lstrip("@") if platform != "אחר" else profile.strip()


def load_logo(upload, size: int, circular: bool) -> Image.Image | None:
    if upload is None: return None
    try:
        logo = Image.open(upload).convert("RGBA")
        logo.thumbnail((max(24, size // 5), max(24, size // 5)), Image.Resampling.LANCZOS)
        if circular:
            mask = Image.new("L", logo.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, logo.width - 1, logo.height - 1), fill=255)
            logo.putalpha(mask)
        return logo
    except (OSError, ValueError):
        st.error("לא ניתן לקרוא את קובץ הלוגו. יש להעלות PNG או JPG תקין.")
        return None


def render_qr(payload: str, size: int, fg: str, bg: str, ec: int, border: int, logo: Image.Image | None) -> tuple[Image.Image, qrcode.QRCode]:
    qr = qrcode.QRCode(version=None, error_correction=ec, box_size=10, border=border)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color=fg, back_color=bg).convert("RGB")
    image = image.resize((size, size), Image.Resampling.NEAREST)
    if logo:
        logo = logo.copy()
        # Opaque backing preserves contrast behind the logo and its quiet margin.
        pad = max(4, size // 100)
        backing = Image.new("RGBA", (logo.width + 2 * pad, logo.height + 2 * pad), bg)
        backing.alpha_composite(logo, (pad, pad))
        if logo.mode == "RGBA" and logo.getchannel("A").getextrema()[0] == 0 and logo.size[0] == logo.size[1]:
            mask = Image.new("L", backing.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, backing.width - 1, backing.height - 1), fill=255)
            backing.putalpha(mask)
        image.paste(backing.convert("RGB"), ((size - backing.width) // 2, (size - backing.height) // 2))
    return image, qr


def svg_bytes(qr: qrcode.QRCode, fg: str, bg: str, logo: Image.Image | None) -> bytes:
    matrix = qr.get_matrix()
    n = len(matrix)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{n}" height="{n}" viewBox="0 0 {n} {n}">',
             f'<rect width="100%" height="100%" fill="{html.escape(bg)}"/>', f'<path fill="{html.escape(fg)}" d="']
    parts.extend(f'M{x} {y}h1v1h-1z' for y, row in enumerate(matrix) for x, dark in enumerate(row) if dark)
    parts.append('"/>')
    if logo:
        buf = io.BytesIO(); logo.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        width, height = n * .2, n * .2
        clip = '<defs><clipPath id="c"><circle cx="50%" cy="50%" r="50%"/></clipPath></defs>' if st.session_state.round_logo else ""
        parts += [clip, f'<image x="{(n-width)/2}" y="{(n-height)/2}" width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet" xlink:href="data:image/png;base64,{b64}"' + (' clip-path="url(#c)"' if st.session_state.round_logo else '') + '/>']
    parts.append('</svg>')
    return "".join(parts).encode("utf-8")


def pdf_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(image.width, image.height))
    pdf.drawImage(ImageReader(image), 0, 0, width=image.width, height=image.height)
    pdf.showPage(); pdf.save()
    return buffer.getvalue()


init_state(); rtl()
st.markdown('<div class="brand"><span class="brand-icon">▦</span><span>QRcraft</span></div><div class="tagline">קוד QR חכם. בדיוק כמו שאתם צריכים.</div>',unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>מה תרצו ליצור היום?</h1></div>',unsafe_allow_html=True)
# Two centered rows of six content type choices.
for row_start in (0,6):
    cols=st.columns(6,gap="small")
    for col,kind in zip(cols,CONTENT_TYPES[row_start:row_start+6]):
        with col:
            if st.button(kind,key="type_"+kind,use_container_width=True,type="primary" if st.session_state.kind==kind else "secondary"):
                st.session_state.kind=kind; st.rerun()

st.markdown('<div class="section-title">🔗　תוכן הקוד</div>',unsafe_allow_html=True)
with st.container(border=True):
    payload=content_form(st.session_state.kind)
    if payload:
        with st.expander("הנתונים שיקודדו"):
            st.code(payload,language=None,wrap_lines=True)

st.markdown('<div class="section-title">🎨　התאמה אישית</div>',unsafe_allow_html=True)
with st.container(border=True):
    c1,c2=st.columns(2)
    with c1: st.color_picker("צבע הקוד",key="fg")
    with c2: st.color_picker("צבע הרקע",key="bg")
    st.slider("גודל (פיקסלים)",200,800,key="size",step=20)
    st.slider("שוליים (פיקסלים)",0,12,key="border")
    st.selectbox("רמת תיקון שגיאות",list(ERROR_LEVELS),key="ec")
    upload=st.file_uploader("העלאת לוגו",type=["png","jpg","jpeg"],key="logo_upload")
    st.toggle("לוגו עגול",key="round_logo")

st.markdown('<div class="section-title">◉　תצוגה מקדימה</div>',unsafe_allow_html=True)
with st.container(border=True):
    if not payload:
        st.info("מלאו את פרטי התוכן כדי ליצור תצוגה מקדימה.")
    else:
        try:
            logo=load_logo(upload,st.session_state.size,st.session_state.round_logo)
            qr_image,qr_obj=render_qr(payload,st.session_state.size,st.session_state.fg,st.session_state.bg,ERROR_LEVELS[st.session_state.ec],st.session_state.border,logo)
            _,center,_=st.columns([1,2,1]); center.image(qr_image,use_container_width=True)
            png=io.BytesIO(); qr_image.save(png,format="PNG")
            jpeg=io.BytesIO(); qr_image.save(jpeg,format="JPEG",quality=95,optimize=True)
            svg=svg_bytes(qr_obj,st.session_state.fg,st.session_state.bg,logo)
            pdf=pdf_bytes(qr_image)
            history_signature=(payload,st.session_state.kind,st.session_state.size,st.session_state.fg,st.session_state.bg,st.session_state.ec,st.session_state.border,upload.name if upload else None)
            if not st.session_state.history or st.session_state.history[0]["signature"]!=history_signature:
                st.session_state.history.insert(0,{"signature":history_signature,"kind":st.session_state.kind,"image":png.getvalue(),"created":datetime.now().strftime("%H:%M")}); st.session_state.history=st.session_state.history[:5]
            d1,d2,d3=st.columns(3)
            d1.download_button("↓　PNG",png.getvalue(),"qr-code.png","image/png",use_container_width=True)
            d2.download_button("↓　SVG",svg,"qr-code.svg","image/svg+xml",use_container_width=True)
            d3.download_button("↓　PDF",pdf,"qr-code.pdf","application/pdf",use_container_width=True)
        except (qrcode.exceptions.DataOverflowError,ValueError) as exc:
            st.error(f"לא ניתן ליצור QR מהתוכן הזה. נסו לקצר אותו. ({exc})")
if st.session_state.history:
    st.caption("הקודים האחרונים שנוצרו")
    hcols=st.columns(min(5,len(st.session_state.history)))
    for col,item in zip(hcols,st.session_state.history):
        with col: st.image(item["image"],use_container_width=True); st.caption(item["kind"])
