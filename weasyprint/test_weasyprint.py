#!/usr/bin/env python3
"""Test WeasyPrint by converting a Wikipedia page to PDF."""

from weasyprint import HTML

URL = "https://en.wikipedia.org/wiki/Attention_deficit_hyperactivity_disorder"
OUTPUT_FILE = "adhd_wikipedia.pdf"


def main():
    print(f"Fetching and converting: {URL}")
    print("This may take a moment...")

    html = HTML(url=URL)
    html.write_pdf(OUTPUT_FILE)

    print(f"PDF saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
