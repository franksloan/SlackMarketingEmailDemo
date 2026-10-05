import logging

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# The google-genai SDK emits an AFC warning via logging when generate_content is
# called without an explicit AutomaticFunctionCallingConfig, even when no tools
# are configured. This is a known SDK bug (googleapis/python-genai#2902).
# LangChain has no way to pass AutomaticFunctionCallingConfig(disable=True) through
# its API, so we suppress only this specific log record.
class _AFCWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "automatic function calling" not in record.getMessage().lower()

logging.getLogger("google.genai.models").addFilter(_AFCWarningFilter())

llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")
