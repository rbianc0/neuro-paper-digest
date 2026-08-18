import json

from neuro_digest.summaries import OpenAISummarizer


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "papers": [
                                        {
                                            "paper_id": "paper-1",
                                            "summary": "A concise supported summary.",
                                            "why_recommended": "It matches the user's research interests.",
                                        }
                                    ]
                                }
                            ),
                        }
                    ],
                }
            ]
        }


class FakeSession:
    def __init__(self):
        self.call = None

    def post(self, url, **kwargs):
        self.call = (url, kwargs)
        return FakeResponse()


def test_summarizer_uses_luna_with_xhigh_reasoning(monkeypatch):
    monkeypatch.delenv("NEUROFEED_SUMMARY_MODEL", raising=False)
    monkeypatch.delenv("NEUROFEED_SUMMARY_REASONING_EFFORT", raising=False)
    session = FakeSession()
    summarizer = OpenAISummarizer(api_key="test-key", session=session)

    output = summarizer.summarize(
        [
            {
                "paper_id": "paper-1",
                "title": "Example paper",
                "abstract": "Example abstract.",
                "journal": "Example Journal",
                "authors": [{"name": "A. Scientist"}],
            }
        ],
        {
            "paper-1": {
                "semantic_score": 0.9,
                "bluesky_score": 0.3,
                "fit_score": 0.8,
                "quality_score": 0.7,
                "broad_discovery_score": 0.1,
                "lane": "focused",
                "provenance": {},
            }
        },
    )

    assert output["paper-1"].summary == "A concise supported summary."
    url, kwargs = session.call
    assert url == "https://api.openai.com/v1/responses"
    assert kwargs["json"]["model"] == "gpt-5.6-luna"
    assert kwargs["json"]["reasoning"] == {"effort": "xhigh"}
    assert kwargs["json"]["text"]["format"]["type"] == "json_schema"
