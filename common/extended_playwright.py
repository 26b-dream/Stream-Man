from __future__ import annotations

# Standard Library
# StandardLibrary
import time

# Third Party
# Imported just to export
from playwright.sync_api import sync_playwright  # type: ignore # noqa 401
from playwright.sync_api._generated import ElementHandle, Page

# Common
from common.extend_class import extend_class


class ExtendedPage(Page):
    def click_if_exists(self: Page, selector: str) -> bool:
        if self.query_selector(selector):
            self.click(selector)
            return True
        else:
            return False

    def click_while_exists(self: Page, selector: str, sleep_time: int = 5) -> None:
        while True:
            element = self.query_selector(selector)
            if element:
                self.click(selector)
                time.sleep(sleep_time)
            else:
                break

    def strict_query_selector(self: Page, selector: str) -> ElementHandle:
        output = self.query_selector(selector)
        if output:
            return output
        else:
            raise ValueError(f"Could not find element with selector: {selector}")


ORIGINAL_PAGE_FUNCTIONS = dir(Page)
extend_class(Page, ExtendedPage)


class ExtendedElementHandle(ElementHandle):
    def strict_get_attribute(self: ElementHandle, name: str) -> str:
        output = self.get_attribute(name)
        if output:
            return output
        else:
            raise ValueError(f"Could not find attribute with name: {name}")

    def strict_text_content(self: ElementHandle) -> str:
        output = self.text_content()
        if output:
            return output
        else:
            raise ValueError("Could not find text content")


ORIGINAL_ELEMENT_HANDLE_FUNCTIONS = dir(ElementHandle)
extend_class(ElementHandle, ExtendedElementHandle)
