import re
from typing import Dict, Any, Tuple, List, Optional
from telethon import Button
from converter import LinkConverterService


class PostPipeline:
    """
    Transforms text, captions, links, and buttons based on a channel mapping rule.
    Guarantees strict 1-to-1 link replacement and image-caption binding.
    """

    def __init__(self, converter_service: LinkConverterService):
        self.converter = converter_service

    async def process_content(
        self,
        raw_text: str,
        mapping: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[List[Any]]]:
        """
        Executes link extraction, bulk bot conversion, watermark replacements,
        header/footer wrapping, and inline button construction.

        Returns:
            (final_text, primary_original_url, primary_converted_url, buttons_markup)
            Returns (None, None, None, None) if NO convertible links are found.
        """
        text = raw_text or ""
        filter_regex = mapping.get("url_filter_regex") or r"https?://[^\s]+"

        # 1. Find all matching URLs in this specific post
        found_urls = re.findall(filter_regex, text)
        if not found_urls:
            # Strictly return None to signal that this message has no valid links
            return None, None, None, None

        unique_urls = list(dict.fromkeys(found_urls))
        primary_original_url = unique_urls[0]

        # 2. Bulk convert all links in this post in a single shot
        converter_bot = mapping.get("converter_bot")
        converted_map = await self.converter.convert_links_bulk(unique_urls, bot_username=converter_bot)

        # 3. Replace each original link with its exact converted counterpart
        primary_converted_url = None
        for orig_url, conv_url in converted_map.items():
            if conv_url:
                if not primary_converted_url:
                    primary_converted_url = conv_url
                text = text.replace(orig_url, conv_url)

        # 4. Apply Watermark / Promo replacements
        replacements = mapping.get("watermark_replacements", {})
        if isinstance(replacements, dict):
            for old_str, new_str in replacements.items():
                if old_str:
                    text = text.replace(old_str, new_str)

        # 5. Strip unconverted external links if configured
        if mapping.get("strip_unconverted", False):
            all_links = re.findall(r'https?://[^\s]+', text)
            for l in all_links:
                if l not in converted_map.values():
                    text = text.replace(l, "")

        # 6. Apply Header and Footer
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

        # 7. Build Inline Buttons
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
