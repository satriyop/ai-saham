# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- News-based sentiment analysis (`saham sentiment TICKER`)
- `--with-sentiment` flag for risk command
- Keyword-based headline classifier (Indonesian + English)
- Optional AI-based headline classifier
- Google News RSS provider

## [0.1.0] - 2026-01-26

### Added
- Initial release of AI-Saham CLI
- Core technical indicators: SMA, EMA, RSI
- Risk assessment with three profiles: conservative, balanced, aggressive
- Deterministic rule-based analysis engine
- AI-enhanced explanations (optional, off by default)
- Support for multiple AI providers: Claude, OpenAI, Gemini, Ollama
- Local SQLite database for market data caching
- Yahoo Finance data provider for IDX stocks
- Offline-first architecture

### Infrastructure
- Hexagonal architecture with clean separation of concerns
- Domain-driven design with ports and adapters
- Comprehensive test suite (346 tests)
- GitHub Actions CI pipeline

[Unreleased]: https://github.com/anthropics/ai-saham/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/anthropics/ai-saham/releases/tag/v0.1.0
