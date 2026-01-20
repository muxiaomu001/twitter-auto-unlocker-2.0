"""
Plugin config injector (2captcha / YesCaptcha).
Writes API keys and toggles into extension storage at runtime.
"""
from typing import Any, Dict, List

from ..core.config import AppConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)

_TWOCAPTCHA_OPTIONS = "options/options.html"
_YESCAPTCHA_OPTIONS = "option/index.html"


def _normalize_provider(provider: str) -> str:
    value = (provider or "auto").strip().lower()
    if value in ("2captcha", "twocaptcha", "2cap"):
        return "2captcha"
    if value in ("yescaptcha", "yc"):
        return "yescaptcha"
    return "auto"


def _provider_order(provider: str) -> List[str]:
    normalized = _normalize_provider(provider)
    if normalized == "2captcha":
        return ["2captcha"]
    if normalized == "yescaptcha":
        return ["yescaptcha"]
    return ["2captcha", "yescaptcha"]


async def _set_extension_config(
    page,
    *,
    ext_id: str,
    options_path: str,
    payload: Dict[str, Any],
    label: str,
) -> bool:
    url = f"chrome-extension://{ext_id}/{options_path}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warning(f"[plugin] Open {label} options failed: {e}")
        return False

    try:
        await page.evaluate(
            """async (payload) => {
                const getConfig = () => new Promise(resolve => chrome.storage.local.get('config', resolve));
                const setConfig = (config) => new Promise(resolve => chrome.storage.local.set({ config }, resolve));
                const data = await getConfig();
                const current = (data && data.config) ? data.config : {};
                const isObject = (obj) => obj && typeof obj === 'object' && !Array.isArray(obj);
                const deepMerge = (target, source) => {
                    const result = { ...target };
                    for (const key of Object.keys(source)) {
                        const value = source[key];
                        if (isObject(value) && isObject(result[key])) {
                            result[key] = deepMerge(result[key], value);
                        } else {
                            result[key] = value;
                        }
                    }
                    return result;
                };
                const merged = deepMerge(current, payload);
                await setConfig(merged);
                return merged;
            }""",
            payload,
        )
        return True
    except Exception as e:
        logger.warning(f"[plugin] Write {label} config failed: {e}")
        return False


def _build_twocaptcha_payload(config: AppConfig) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "apiKey": config.captcha.get_twocaptcha_key(),
        "isPluginEnabled": True,
    }

    if not config.captcha.plugin_twocaptcha_turnstile_only:
        return payload

    enabled_flags = [
        "enabledForNormal",
        "enabledForRecaptchaV2",
        "enabledForInvisibleRecaptchaV2",
        "enabledForRecaptchaV3",
        "enabledForRecaptchaAudio",
        "enabledForGeetest",
        "enabledForGeetest_v4",
        "enabledForKeycaptcha",
        "enabledForArkoselabs",
        "enabledForLemin",
        "enabledForYandex",
        "enabledForCapyPuzzle",
        "enabledForAmazonWaf",
        "enabledForMTCaptcha",
    ]
    autosolve_flags = [
        "autoSolveNormal",
        "autoSolveRecaptchaV2",
        "autoSolveInvisibleRecaptchaV2",
        "autoSolveRecaptchaV3",
        "autoSolveRecaptchaAudio",
        "autoSolveGeetest",
        "autoSolveKeycaptcha",
        "autoSolveArkoselabs",
        "autoSolveGeetest_v4",
        "autoSolveLemin",
        "autoSolveYandex",
        "autoSolveCapyPuzzle",
        "autoSolveAmazonWaf",
        "autoSolveMTCaptcha",
    ]

    for name in enabled_flags:
        payload[name] = False
    for name in autosolve_flags:
        payload[name] = False

    payload["enabledForTurnstile"] = True
    payload["autoSolveTurnstile"] = True
    return payload


def _build_yescaptcha_payload(config: AppConfig) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "clientKey": config.captcha.get_yescaptcha_key(),
        "autorun": True,
    }

    if not config.captcha.plugin_yescaptcha_funcaptcha_only:
        return payload

    payload.update(
        {
            "hcaptcha": False,
            "imagetotext": False,
            "rainbow": False,
            "isTextCaptcha": False,
            "isOpenCloudflare": False,
            "recaptchaConfig": {"isOpen": False},
            "funcaptchaConfig": {"isOpen": True},
        }
    )
    return payload


async def apply_captcha_plugin_config(browser, config: AppConfig) -> None:
    """Apply plugin config once per browser instance."""
    if not config.captcha.is_plugin_mode():
        return

    if getattr(browser, "_captcha_plugin_configured", False):
        return

    provider_order = _provider_order(config.captcha.plugin_provider)

    try:
        context = browser.context
    except Exception as e:
        logger.warning(f"[plugin] Missing browser context: {e}")
        return

    page = await context.new_page()
    try:
        if "2captcha" in provider_order:
            twocaptcha_key = config.captcha.get_twocaptcha_key()
            ext_id = config.captcha.plugin_twocaptcha_ext_id
            if twocaptcha_key and ext_id:
                payload = _build_twocaptcha_payload(config)
                ok = await _set_extension_config(
                    page,
                    ext_id=ext_id,
                    options_path=_TWOCAPTCHA_OPTIONS,
                    payload=payload,
                    label="2captcha",
                )
                if ok:
                    logger.info("[plugin] 2captcha config updated")
            else:
                logger.warning("[plugin] 2captcha key/ext id missing, skipped")

        if "yescaptcha" in provider_order:
            yescaptcha_key = config.captcha.get_yescaptcha_key()
            ext_id = config.captcha.plugin_yescaptcha_ext_id
            if yescaptcha_key and ext_id:
                payload = _build_yescaptcha_payload(config)
                ok = await _set_extension_config(
                    page,
                    ext_id=ext_id,
                    options_path=_YESCAPTCHA_OPTIONS,
                    payload=payload,
                    label="YesCaptcha",
                )
                if ok:
                    logger.info("[plugin] YesCaptcha config updated")
            else:
                logger.warning("[plugin] YesCaptcha key/ext id missing, skipped")
    finally:
        try:
            await page.close()
        except Exception:
            pass

    setattr(browser, "_captcha_plugin_configured", True)
