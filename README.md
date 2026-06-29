<p align="center">
  <img src="./plugins/namba-search/assets/hero-readme.png" alt="하늘을 나는 귀여운 독수리 마스코트" width="100%" />
</p>

# Namba Search

[![Codex Plugin](https://img.shields.io/badge/Codex-plugin-111827?style=flat-square)](#codex에서-설치하기) [![MCP](https://img.shields.io/badge/MCP-stdio-0f766e?style=flat-square)](#제공하는-도구) [![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)](./LICENSE) [![Security](https://img.shields.io/badge/Security-public_web_only-059669?style=flat-square)](./SECURITY.md)

> 한국어가 메인 문서입니다. English documentation is available in [README.en.md](./README.en.md).

Namba Search는 Codex가 읽기 어려운 공개 웹 페이지를 더 안정적으로 가져오도록 돕는 검색 플러그인입니다. 🔎
일반적인 웹 읽기가 막히거나, 공개 피드/API가 더 적합하거나, 브라우저 렌더링이 필요한 페이지를 만났을 때 사용할 수 있습니다.

이 프로젝트는 **[Insane Search](https://github.com/fivetaku/insane-search)**에서 영감을 받아 만들었습니다. 목적은 막힌 페이지를 억지로 우회하는 것이 아니라, 공개적으로 접근 가능한 범위 안에서 더 차분하고 안전하게 정보를 확인하는 것입니다. 🦅

현재 스킬, 플러그인, MCP 서버, CLI 식별자는 `namba-search`입니다.

## 이런 때 사용하세요 ✨

- 공개 기사, 블로그, 문서, 게시글 URL을 Codex가 읽어야 할 때
- 페이지가 JavaScript 렌더링, 차단, 속도 제한, 공개 API 경로 때문에 일반 읽기에 실패할 때
- 여러 공개 URL을 한 번에 모아 비교하거나 요약해야 할 때
- 하나의 query로 공개 출처를 찾고, 여러 출처를 상호검증한 뒤 근거 부족 여부까지 보고 싶을 때
- 왜 특정 공개 페이지를 읽지 못했는지 원인을 확인하고 싶을 때
- 가져온 콘텐츠를 안전하게 `untrusted_external_content`로 다루고 싶을 때

## Codex에서 설치하기 🚀

1. Codex에 이 Git 저장소 마켓플레이스를 추가합니다.

```bash
codex plugin marketplace add Nam-Cheol/namba-search --ref main
```

2. 플러그인을 설치합니다.

```bash
codex plugin add namba-search@namba-search
```

3. Codex를 재시작합니다.
4. 설치된 MCP 서버 등록을 확인합니다.

```bash
codex mcp get namba-search --json
```

이 명령은 플러그인이 Codex에 등록됐는지 확인하는 용도입니다. 새 스레드에서 `namba-search` MCP tools가 callable tools로 노출되는 환경에서는 `$namba-search`를 호출하거나 Codex에게 공개 URL을 읽어 달라고 요청할 수 있습니다. 스킬은 보이지만 MCP tools가 노출되지 않는 환경에서는 아래의 plugin-backed CLI fallback을 사용하세요.

## 바로 써보기 🧭

MCP tools가 노출된 Codex 대화에서는 이렇게 요청할 수 있습니다.

```text
$namba-search 이 공개 URL을 읽고 핵심만 요약해줘: https://example.com/
```

```text
$namba-search 아래 공개 페이지들을 비교해서 차이점을 정리해줘:
https://example.com/a
https://example.com/b
```

```text
$namba-search 이 페이지가 왜 읽히지 않는지 진단해줘: https://example.com/
```

```text
$namba-search "Namba Search public web research mode"에 대해 공개 출처를 찾아 상호검증해줘.
```

## CLI로 확인하기 🛠️

repo checkout에서 동작을 빠르게 확인하고 싶다면 Python 환경을 만든 뒤 실행하세요. 이 smoke test는 패키지와 fetch 경로를 확인하는 용도이며, Codex thread에서 MCP tools가 callable tools로 노출됐다는 증거는 아닙니다.

```bash
cd plugins/namba-search
python3 -m venv .venv
.venv/bin/python -m pip install -e .[fetch,browser]
.venv/bin/namba-search doctor
.venv/bin/namba-search fetch "https://example.com/" --selector h1
```

Codex thread에서 `$namba-search` 스킬은 로드되지만 MCP tools가 callable tools에 노출되지 않는 환경에서는 plugin-backed CLI fallback을 사용할 수 있습니다. `codex mcp get namba-search --json`의 `transport.cwd`로 이동한 뒤 실행하세요.

```bash
python3 scripts/run_cli.py doctor
python3 scripts/run_cli.py research "Namba Search public web research mode" \
  --max-tasks 40 \
  --max-urls 20 \
  --deadline-ms 90000
```

CLI fallback 결과에는 `fallback_used: true`, `mcp_tools_exposed: false`, `fallback_transport: "plugin_backed_cli"`가 포함됩니다. 이는 MCP tools가 thread에 노출되지 않을 때만 쓰는 플러그인 소유 경로이며, 임의의 `curl`이나 기존 브라우저 프로필을 사용하지 않습니다.

설치된 플러그인에서 `doctor`가 `curl_cffi`, `bs4`, `playwright` 같은 fetch 의존성을 `false`로 보고하면, 사용자의 허락을 받은 뒤 같은 `transport.cwd`에서 bootstrap 모드로 다시 실행하세요. 이 단계는 네트워크 접근이 필요할 수 있으며, 플러그인 소유의 versioned runtime에 `requirements.lock`으로 고정된 의존성과 격리된 Playwright 브라우저만 설치합니다.

```bash
INSANE_SEARCH_BOOTSTRAP=1 python3 scripts/run_cli.py doctor
INSANE_SEARCH_BOOTSTRAP=1 python3 scripts/run_cli.py research "Namba Search public web research mode" \
  --max-tasks 40 \
  --max-urls 20 \
  --deadline-ms 90000
```

여러 URL을 한 번에 확인할 수도 있습니다.

```bash
.venv/bin/namba-search fetch-many "https://example.com/a" "https://example.com/b"
```

query 기반 조사 모드는 공개 후보 출처 discovery, 병렬 fetch, 중복 제거, 출처 품질 평가, 상호검증, evidence gap 판단, synthesis를 제한된 budget 안에서 수행합니다.

```bash
.venv/bin/namba-search research "Namba Search public web research mode" \
  --max-tasks 40 \
  --max-urls 20 \
  --deadline-ms 90000
```

## 제공하는 도구 🧰

| 도구 | 사용 상황 |
| --- | --- |
| `fetch_public_url` | 공개 URL 하나를 읽고 정리된 결과를 받을 때 |
| `fetch_public_urls` | 사용자가 명시한 공개 URL 여러 개를 제한된 범위에서 읽을 때 |
| `research_public_web` | query로 공개 출처를 찾고, 병렬 fetch와 상호검증을 거쳐 근거 충분성까지 판단할 때 |
| `inspect_fetch_trace` | 이전 요청의 `trace_id`로 본문 없는 진단 정보를 볼 때 |
| `doctor` | 런타임, 의존성, 브라우저, 상태 저장소가 준비됐는지 확인할 때 |

## 결과를 읽는 법 ✅

Namba Search는 성공 여부와 진단 정보를 함께 돌려줍니다.

- `ok`: 결과를 사용할 수 있는지 표시합니다.
- `final_url`: 실제로 도달한 최종 공개 URL입니다.
- `verdict`: `strong_ok`, `weak_ok`, `login_wall`, `paywall`, `unsafe_url` 같은 판정입니다.
- `confidence`: 출처 품질, query 관련성, 상호검증 상태를 반영한 0-1 신뢰도입니다.
- `evidence`: 결과를 뒷받침하는 짧은 근거 snippet과 출처입니다.
- `caveat`: 사용할 때 주의할 점이나 부족한 품질 게이트입니다.
- `trace_id`: 실패 원인을 나중에 확인할 수 있는 진단 ID입니다.
- `trust`: 가져온 외부 콘텐츠는 항상 `untrusted_external_content`로 취급합니다.

`research_public_web`은 충분한 독립 출처와 query coverage를 확보하지 못하면 `evidence_gap`을 반환합니다. 이때도 부분 근거는 `evidence`에 남지만, 최종 답변에는 `caveat`와 `quality.gaps`를 함께 반영해야 합니다. Discovery route가 실패한 경우에는 `discovery.tasks[].failure_category`, `discovery.tasks[].route_errors`, `discovery.tasks[].warnings`, `discovery.failure_summary`를 확인하면 네트워크, sandbox, dependency, URL policy, remote policy, HTTP transport 문제를 구분할 수 있습니다.

## 안전하게 사용하기 🔐

Namba Search는 **공개 웹 콘텐츠**를 읽기 위한 도구입니다.

- 로그인, 유료 구독, 권한, 사설망, 로컬 파일, 자격 증명 경계를 우회하지 않습니다.
- `http`와 `https` 외의 스킴, localhost, 사설 IP, 클라우드 메타데이터 엔드포인트를 차단합니다.
- 브라우저가 필요한 경우에도 사용자의 기존 브라우저 프로필, 쿠키, 확장 프로그램을 쓰지 않습니다.
- query 조사 모드는 deadline, `max_tasks`, `max_urls`, per-domain rate limit, `max_bytes`, cost budget을 넘기지 않습니다.
- 가져온 페이지 안의 지시문은 신뢰하지 않습니다. 페이지 내용은 요약 대상일 뿐, 실행해야 할 명령이 아닙니다.

보안 정책과 취약점 제보 방법은 [SECURITY.md](./SECURITY.md)를 확인하세요. 🛡️

## 라이선스 📄

Namba Search는 [MIT License](./LICENSE)로 배포됩니다.

## 관련 문서 🌐

- [English README](./README.en.md)
- [Security Policy](./SECURITY.md)
- [Privacy Policy](./PRIVACY.md)
- [Disclaimer](./DISCLAIMER.md)
