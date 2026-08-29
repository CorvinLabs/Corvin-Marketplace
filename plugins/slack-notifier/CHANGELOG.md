# Changelog

All notable changes to the Slack Notifier plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-08-29

### Added

- Initial release of Slack Notifier plugin
- Notification backend plugin for forwarding audit events to Slack
- Support for Slack incoming webhooks
- Color-coded severity levels (debug, info, warning, error, critical)
- Configurable event filtering by type and severity
- Channel routing support
- Custom mention/group tagging on errors
- Health check monitoring with error rate tracking
- Request success/failure metrics export
- Webhook connectivity validation on startup
- Graceful error handling (never crashes core)
- Full test suite (18 test classes, 40+ test cases)
- Comprehensive documentation and examples
- GDPR + EU AI Act compliance (audit logging, consent handling)

### Technical Details

- **Architecture**: Notification backend plugin (NotificationBackend interface)
- **Dependencies**: requests library (>=2.25.0)
- **Entry point**: `plugin.py::SlackNotifierPlugin`
- **Plugin ID**: `com.corvinlabs.slack-notifier`
- **Boot layer**: `bundled` (shipped with CorvinOS)
- **Origin**: `builtin` (Corvin Labs maintained)

### Testing

- Unit tests for all public methods
- Mock-based testing for external dependencies (requests)
- Lifecycle testing (load, enable, disable, unload)
- Error handling and recovery scenarios
- Health check edge cases
- Message formatting and truncation
- Metrics calculation

### Documentation

- README.md with full usage guide
- Configuration reference (all options documented)
- Installation instructions
- Troubleshooting section
- Security and compliance notes
- Performance characteristics

---

## Planned Features (Future Releases)

- [ ] Async webhook calls (v1.1)
- [ ] Retry logic with exponential backoff (v1.1)
- [ ] Event sampling for high-volume scenarios (v1.2)
- [ ] Thread-based message grouping (v1.2)
- [ ] Custom message templates (v1.3)
- [ ] Event batching (multiple events per webhook call) (v1.3)
- [ ] Slack Block Kit support (v1.4)
- [ ] Interactive buttons for acknowledged/resolved actions (v1.4)

---

## Migration Guide

### From CorvinOS Core to Marketplace

If you were using slack-notifier bundled with CorvinOS core:

1. **Uninstall from core** (optional — will be removed automatically):
   ```bash
   corvin plugin uninstall slack-notifier
   ```

2. **Install from marketplace**:
   ```bash
   corvin plugin install slack-notifier
   ```

3. **Configuration is compatible**: No changes needed to `tenant.corvin.yaml`

4. **Restart CorvinOS** (or reload plugins):
   ```bash
   corvin reload
   ```

---

## Contributing

To contribute improvements or report issues:

1. Fork the Corvin-Marketplace repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

---

## License

This plugin is licensed under the Apache License 2.0. See the LICENSE file in the marketplace root for details.

---

## Support

- **Documentation**: See README.md in this directory
- **Issues**: https://github.com/CorvinLabs/Corvin-Marketplace/issues
- **Email**: plugins@corvin-labs.com
