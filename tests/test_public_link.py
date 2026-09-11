import logging
import unittest

from proxy.utils import DomainCensorFilter


def _filtered_message(msg, *args, **extra):
    record = logging.LogRecord("test", logging.INFO, __file__, 1, msg, args, None)
    record.__dict__.update(extra)
    DomainCensorFilter().filter(record)
    return record.getMessage()


class ConnectLinkCensorTest(unittest.TestCase):
    def test_domains_are_censored_by_default(self):
        self.assertEqual(
            _filtered_message("  Fake TLS:      %s", "example.com"),
            "  Fake TLS:      exa****.com",
        )

    def test_uncensored_record_keeps_public_host(self):
        link = "tg://proxy?server=example.com&port=443&secret=dd" + "0" * 32
        self.assertEqual(
            _filtered_message("    %s", link, uncensored=True),
            "    " + link,
        )


if __name__ == "__main__":
    unittest.main()
