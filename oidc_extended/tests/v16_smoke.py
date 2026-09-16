"""Focused regressions for the v16 ports. External AI/AWS calls are simulated."""
import importlib
import io
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.model.base_document import get_controller


def run(app):
    assert app in frappe.get_installed_apps()
    modules = frappe.get_all('Module Def', filters={'app_name': app}, pluck='name')
    doctypes = frappe.get_all('DocType', filters={'module': ['in', modules]}, pluck='name')
    for doctype in doctypes:
        frappe.get_meta(doctype)
        get_controller(doctype)
    globals()['check_' + app]()
    print({'app': app, 'controllers': len(doctypes), 'regressions': 'passed'})


def check_oidc_extended():
    from oidc_extended.callback import custom
    from frappe.utils.oauth import create_oauth_state, consume_oauth_state
    with patch('oidc_extended.callback.get_info_via_oauth') as exchange, patch('frappe.respond_as_web_page') as response:
        custom('unused', 'unrecognized-state')
        exchange.assert_not_called()
        assert response.call_args.kwargs['http_status_code'] == 417
        state = create_oauth_state('/app')
        assert consume_oauth_state(state) == '/app'
        custom('unused', state)
        exchange.assert_not_called()
        assert response.call_args.kwargs['http_status_code'] == 417
