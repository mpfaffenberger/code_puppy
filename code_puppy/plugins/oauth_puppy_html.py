"""Shared Mist HTML templates for OAuth completion pages."""

from __future__ import annotations

from typing import Optional, Tuple

CLAUDE_LOGO_URL = "https://voideditor.com/claude-icon.png"
CHATGPT_LOGO_URL = (
    "https://freelogopng.com/images/all_img/1681038325chatgpt-logo-transparent.png"
)
GEMINI_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Google_Gemini_logo.svg/512px-Google_Gemini_logo.svg.png"


def oauth_success_html(service_name: str, extra_message: Optional[str] = None) -> str:
    """Return the Mist OAuth success page."""
    clean_service = service_name.strip() or "OAuth"
    detail = f"<p class='detail'>💨 {extra_message} 💨</p>" if extra_message else ""
    projectile, rival_url, rival_alt, target_modifier = _service_targets(clean_service)
    target_classes = "target" if not target_modifier else f"target {target_modifier}"
    return (
        "<!DOCTYPE html>"
        "<html lang='en'><head><meta charset='utf-8'>"
        "<title>Mist OAuth Complete</title>"
        "<style>"
        "html,body{margin:0;padding:0;height:100%;overflow:hidden;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f172a 0%,#111827 45%,#1f2937 100%);color:#e5e7eb;}"
        "body{display:flex;align-items:center;justify-content:center;}"
        ".mist-card{position:relative;width:90%;max-width:880px;padding:60px;background:rgba(15,23,42,0.72);border-radius:32px;backdrop-filter:blur(14px);box-shadow:0 30px 90px rgba(8,11,18,0.7);text-align:center;border:1px solid rgba(148,163,184,0.25);}"
        "h1{font-size:3.4em;margin:0;color:#f1f5f9;text-shadow:0 14px 40px rgba(8,11,18,0.55);letter-spacing:1px;}"
        "p{font-size:1.25em;margin:16px 0;color:#cbd5f5;}"
        ".detail{font-size:1.1em;opacity:0.9;}"
        ".mega{display:inline-block;font-size:1.35em;margin-top:14px;color:#f97316;}"
        ".confetti{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:200%;height:200%;pointer-events:none;mix-blend-mode:screen;}"
        ".confetti span{position:absolute;font-size:3.4em;animation:floaty 6s ease-in-out infinite;color:#fbbf24;}"
        "@keyframes floaty{0%,100%{transform:translate3d(0,0,0) rotate(0deg);}35%{transform:translate3d(0,-70px,0) rotate(10deg);}65%{transform:translate3d(0,-90px,0) rotate(-12deg);}90%{transform:translate3d(0,-60px,0) rotate(6deg);}}"
        ".confetti span:nth-child(odd){animation-duration:7.2s;}"
        ".confetti span:nth-child(3n){animation-duration:8.6s;}"
        ".confetti span:nth-child(4n){animation-duration:5.9s;}"
        ".confetti span:nth-child(5n){animation-duration:9.4s;}"
        ".artillery{position:absolute;bottom:12%;left:0;width:100%;max-width:1100px;height:240px;pointer-events:none;overflow:visible;}"
        ".artillery .cannon{position:absolute;bottom:0;font-size:3.4em;color:#f97316;filter:drop-shadow(0 12px 32px rgba(249,115,22,0.45));}"
        ".artillery .cannon.left{left:4%;}"
        ".artillery .cannon.right{left:12%;transform:rotate(-4deg);}"
        ".artillery .shell{position:absolute;left:10%;font-size:2.6em;animation:strafe 2.6s ease-out infinite;color:#facc15;text-shadow:0 0 14px rgba(250,204,21,0.45);}"
        "@keyframes strafe{0%{left:10%;opacity:1;}60%{left:72%;opacity:1;}100%{left:82%;opacity:0;}}"
        ".target{position:absolute;top:175px;right:-10%;width:220px;filter:drop-shadow(0 24px 46px rgba(8,11,18,0.72));animation:targetShake 1.9s ease-in-out infinite;}"
        ".target img{width:200px;height:auto;border-radius:18px;background:#0f172a;padding:16px;border:1px solid rgba(148,163,184,0.35);}"
        ".target.invert img{filter:brightness(1.2) saturate(1.15);background:rgba(15,23,42,0.9);}"
        "@keyframes targetShake{0%,100%{transform:rotate(0deg) scale(1);}30%{transform:rotate(-4deg) scale(1.05);}60%{transform:rotate(3deg) scale(0.97);}85%{transform:rotate(-2deg) scale(1.04);}}"
        ".target::after{content:'';position:absolute;top:50%;left:50%;width:220px;height:220px;border-radius:50%;background:radial-gradient(circle,rgba(248,113,113,0.35)0%,rgba(248,113,113,0)70%);transform:translate(-50%,-50%) scale(0);animation:impact 2.6s ease-out infinite;opacity:0;mix-blend-mode:screen;}"
        "@keyframes impact{0%,60%{transform:translate(-50%,-50%) scale(0);opacity:0;}70%{transform:translate(-50%,-50%) scale(1.2);opacity:1;}100%{transform:translate(-50%,-50%) scale(1.5);opacity:0;}}"
        "</style>"
        "</head><body>"
        "<div class='mist-card'>"
        "<div class='confetti'>"
        + "".join(
            f"<span style='left:{left}%;top:{top}%;animation-delay:{delay}s;'>{emoji}</span>"
            for left, top, delay, emoji in _SUCCESS_PARTICLES
        )
        + "</div>"
        f"<h1>💨⚡ {clean_service} OAuth Complete ⚡💨</h1>"
        "<p class='mega'>Authentication completed successfully.</p>"
        f"{detail}"
        f"<p>Mist is now connected to {rival_alt}.</p>"
        "<p>🚀 This window will close automatically. 🚀</p>"
        f"<div class='{target_classes}'><img src='{rival_url}' alt='{rival_alt}'></div>"
        "<div class='artillery'>" + _build_artillery(projectile) + "</div>"
        "</div>"
        "<script>setTimeout(()=>window.close(),3500);</script>"
        "</body></html>"
    )


def oauth_failure_html(service_name: str, reason: str) -> str:
    """Return the Mist OAuth failure page."""
    clean_service = service_name.strip() or "OAuth"
    clean_reason = reason.strip() or "Authentication did not complete"
    projectile, rival_url, rival_alt, target_modifier = _service_targets(clean_service)
    target_classes = "target" if not target_modifier else f"target {target_modifier}"
    return (
        "<!DOCTYPE html>"
        "<html lang='en'><head><meta charset='utf-8'>"
        "<title>Mist Tears</title>"
        "<style>"
        "html,body{margin:0;padding:0;height:100%;overflow:hidden;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:linear-gradient(160deg,#101827 0%,#0b1120 100%);color:#e2e8f0;}"
        "body{display:flex;align-items:center;justify-content:center;}"
        ".mist-card{position:relative;width:90%;max-width:780px;padding:55px;background:rgba(10,13,23,0.78);border-radius:30px;box-shadow:0 26px 80px rgba(2,6,23,0.78);text-align:center;border:1px solid rgba(71,85,105,0.35);}"
        "h1{font-size:3em;margin:0 0 14px;text-shadow:0 16px 36px rgba(15,23,42,0.7);color:#f87171;}"
        "p{font-size:1.2em;margin:14px 0;line-height:1.6;color:#cbd5f5;}"
        ".howl{font-size:1.35em;margin:18px 0;color:#fda4af;}"
        ".tearstorm{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:190%;height:190%;pointer-events:none;mix-blend-mode:screen;}"
        ".tearstorm span{position:absolute;font-size:3.2em;animation:weep 4.8s ease-in-out infinite;color:#60a5fa;}"
        "@keyframes weep{0%{transform:translate3d(0,-10px,0) rotate(-6deg);opacity:0.85;}35%{transform:translate3d(-20px,18px,0) rotate(8deg);opacity:1;}65%{transform:translate3d(25px,28px,0) rotate(-12deg);opacity:0.8;}100%{transform:translate3d(0,60px,0) rotate(0deg);opacity:0;}}"
        ".tearstorm span:nth-child(odd){animation-duration:5.8s;}"
        ".tearstorm span:nth-child(3n){animation-duration:6.4s;}"
        ".tearstorm span:nth-child(4n){animation-duration:7.3s;}"
        ".buttons{margin-top:26px;}"
        ".buttons a{display:inline-block;margin:6px 12px;padding:12px 28px;border-radius:999px;background:rgba(59,130,246,0.16);color:#bfdbfe;text-decoration:none;font-weight:600;border:1px solid rgba(96,165,250,0.4);transition:all 0.3s;}"
        ".buttons a:hover{background:rgba(96,165,250,0.28);transform:translateY(-2px);}"
        ".battlefield{position:absolute;bottom:-25px;left:0;width:100%;max-width:960px;height:220px;pointer-events:none;}"
        ".battlefield .shell{position:absolute;left:10%;font-size:2.4em;color:#38bdf8;text-shadow:0 0 12px rgba(56,189,248,0.45);animation:strafeSad 3s ease-out infinite;}"
        "@keyframes strafeSad{0%{left:10%;opacity:1;}65%{left:70%;opacity:1;}100%{left:80%;opacity:0;}}"
        ".battlefield .target{position:absolute;top:16px;right:6%;width:220px;filter:drop-shadow(0 20px 44px rgba(2,6,23,0.78));animation:sway 2s ease-in-out infinite;}"
        ".battlefield .target img{width:200px;height:auto;border-radius:18px;background:#0b1120;padding:16px;border:1px solid rgba(96,165,250,0.4);}"
        ".battlefield .target.invert img{filter:brightness(1.2) saturate(1.15);background:rgba(15,23,42,0.9);}"
        "@keyframes sway{0%,100%{transform:rotate(0deg);}40%{transform:rotate(-6deg);}70%{transform:rotate(5deg);}}"
        "</style>"
        "</head><body>"
        "<div class='mist-card'>"
        "<div class='tearstorm'>"
        + "".join(
            f"<span style='left:{left}%;top:{top}%;animation-delay:{delay}s;'>{emoji}</span>"
            for left, top, delay, emoji in _FAILURE_PARTICLES
        )
        + "</div>"
        f"<h1>💔💨 {clean_service} OAuth Whoopsie 💔</h1>"
        "<p class='howl'>Authentication could not be completed.</p>"
        f"<p>{clean_reason}</p>"
        "<p>Return to Mist and try the authentication flow again.</p>"
        "<div class='buttons'>"
        "<a href='https://github.com/bajajra/mist' target='_blank'>Mist on GitHub</a>"
        "</div>"
        "<div class='battlefield'>"
        + _build_artillery(projectile, shells_only=True)
        + f"<div class='{target_classes}'><img src='{rival_url}' alt='{rival_alt}'></div>"
        + "</div>"
        "</div>"
        "</body></html>"
    )


_SUCCESS_PARTICLES = (
    (5, 12, 0.0, "💨"),
    (18, 28, 0.2, "💨"),
    (32, 6, 1.1, "✨"),
    (46, 18, 0.5, "✦"),
    (62, 9, 0.8, "💨"),
    (76, 22, 1.3, "💨"),
    (88, 14, 0.4, "⚡"),
    (12, 48, 0.6, "💨"),
    (28, 58, 1.7, "◆"),
    (44, 42, 0.9, "✦"),
    (58, 52, 1.5, "💨"),
    (72, 46, 0.3, "✨"),
    (86, 54, 1.1, "💨"),
    (8, 72, 0.7, "💨"),
    (24, 80, 1.2, "✨"),
    (40, 74, 0.2, "💨"),
    (56, 66, 1.6, "✦"),
    (70, 78, 1.0, "💨"),
    (84, 70, 1.4, "💨"),
    (16, 90, 0.5, "💨"),
    (32, 92, 1.9, "◆"),
    (48, 88, 1.1, "⚡"),
    (64, 94, 1.8, "✨"),
    (78, 88, 0.6, "💨"),
    (90, 82, 1.3, "💨"),
)


_FAILURE_PARTICLES = (
    (8, 6, 0.0, "🥺💨"),
    (22, 18, 0.3, "😢💨"),
    (36, 10, 0.6, "😿✨"),
    (50, 20, 0.9, "😭✦"),
    (64, 8, 1.2, "🥺💨"),
    (78, 16, 1.5, "😢💨"),
    (12, 38, 0.4, "😭💨"),
    (28, 44, 0.7, "😿✨"),
    (42, 34, 1.0, "🥺✦"),
    (58, 46, 1.3, "😭💨"),
    (72, 36, 1.6, "😢💨"),
    (86, 40, 1.9, "😭💨"),
    (16, 64, 0.5, "🥺✨"),
    (32, 70, 0.8, "😭✦"),
    (48, 60, 1.1, "😿💨"),
    (62, 74, 1.4, "🥺💨"),
    (78, 68, 1.7, "😭💨"),
    (90, 72, 2.0, "😢✨"),
    (20, 88, 0.6, "🥺✦"),
    (36, 92, 0.9, "😭💨"),
    (52, 86, 1.2, "😢💨"),
    (68, 94, 1.5, "😭💨"),
    (82, 90, 1.8, "😿✨"),
)


_STRAFE_SHELLS: Tuple[Tuple[float, float], ...] = (
    (22.0, 0.0),
    (28.0, 0.35),
    (34.0, 0.7),
    (26.0, 0.2),
    (32.0, 0.55),
    (24.0, 0.9),
    (30.0, 1.25),
)


def _build_artillery(projectile: str, *, shells_only: bool = False) -> str:
    """Return HTML spans for mist artillery shells (and cannons when desired)."""
    shell_markup = []
    for index, (top, delay) in enumerate(_STRAFE_SHELLS):
        duration = 2.3 + (index % 3) * 0.25
        shell_markup.append(
            f"<span class='shell' style='top:{top}%;animation-delay:-{delay}s;animation-duration:{duration}s;'>{projectile}💥</span>"
        )
    shells = "".join(shell_markup)
    if shells_only:
        return shells

    cannons = (
        "<span class='cannon left'>💨🧨</span><span class='cannon right'>💨🔥</span>"
    )
    return cannons + shells


def _service_targets(service_name: str) -> Tuple[str, str, str, str]:
    """Map service names to projectile emoji and rival logo metadata."""
    normalized = service_name.lower()
    if "anthropic" in normalized or "claude" in normalized:
        return "💨🧨", CLAUDE_LOGO_URL, "Claude logo", ""
    if "chat" in normalized or "gpt" in normalized:
        return "💨🚀", CHATGPT_LOGO_URL, "ChatGPT logo", "invert"
    if "gemini" in normalized or "google" in normalized:
        return "💨✨", GEMINI_LOGO_URL, "Gemini logo", ""
    return "💨💥", CHATGPT_LOGO_URL, "mystery logo", "invert"
