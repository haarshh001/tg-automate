import re
from typing import Dict, Any, Tuple, List, Optional
from telethon import Button
from converter import LinkConverterService


class PostPipeline:
    """
    Transforms text, captions, links, and buttons based on a channel mapping rule.
    """

    def __init__(self, converter_service: LinkConverterService):
        self.converter = converter_service

    async def process_content(
        self,
        raw_text: str,
        mapping: Dict[str, Any]
    ) -> Tuple[str, Optional[str], Optional[str], List[Any]]:
        """
        Executes link extraction, bot conversion, watermark replacements,
        header/footer wrapping, and inline button construction.

        Returns:
            (final_text, original_url, converted_url, buttons_markup)
        """
        text = raw_text or ""
        filter_regex = mapping.get("url_filter_regex") or r"https?://[^\s]+"

        # 1. Find all matching URLs
        found_urls = re.findall(filter_regex, text)
        primary_original_url = found_urls[0] if found_urls else None
        primary_converted_url = None

        # 2. Convert each unique URL via the specified converter bot
        converter_bot = mapping.get("converter_bot")
        for u in set(found_urls):
            conv_url = await self.converter.convert_link(u, bot_username=converter_bot)
            if conv_url:
                if not primary_converted_url:
                    primary_converted_url = conv_url
                text = text.replace(u, conv_url)

        # 3. Apply Watermark / Promo replacements
        replacements = mapping.get("watermark_replacements", {})
        if isinstance(replacements, dict):
            for old_str, new_str in replacements.items():
                if old_str:
                    text = text.replace(old_str, new_str)

        # 4. Strip unconverted external links if configured
        if mapping.get("strip_unconverted", False):
            # Removes links that were not converted
            all_links = re.findall(r'https?://[^\s]+', text)
            for l in all_links:
                if primary_converted_url and l == primary_converted_url:
                    continue
                text = text.replace(l, "")

        # 5. Apply Header and Footer
        header = mapping.get("header_text", "").strip()
        footer = mapping.get("footer_text", "").strip()

        parts = []
        if header:
            parts.append(header)
        if text.strip():
            parts.append(text.strip())
        if footer:
            parts.append(footer)

        final_text = "\n\n".join(parts) if parts else ""

        # 6. Build Inline Buttons
        buttons_markup = None
        raw_buttons = mapping.get("inline_buttons", [])
        if raw_buttons and isinstance(raw_buttons, list):
            row = []
            for b in raw_buttons:
                b_text = b.get("text", "Click Here")
                b_type = b.get("type", "url")
                b_url = b.get("url", "")

                if b_type == "converted_url":
                    b_url = primary_converted_url or primary_original_url or b_url

                if b_url and (b_url.startswith("http://") or b_url.startswith("https://") or b_url.startswith("tg://")):
                    row.append(Button.url(b_text, b_url))

            if row:
                buttons_markup = [row]

        return final_text, primary_original_url, primary_converted_url, buttons_markup
