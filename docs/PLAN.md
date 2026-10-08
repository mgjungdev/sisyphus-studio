# Sisyphus Studio: 발음(Reading Studio)과 어휘(Vocabulary Studio) 강의를 GitHub Pages 사이트로

## Context
Notion "Sisyphus — English stuff"에는 두 강의가 있다.
- **Reading Studio** (🎙️): 실제로는 발음 강의. 16개 레슨과 참고 3편이 있고, 문장은 `<details><summary>평문</summary>강세 표시본</details>` 형태다. 소리 모델은 없다.
- **Vocabulary Studio** (📚): Day 01–23, 단어 449개.

목표: 두 강의를 정적 사이트로 옮긴다. 발음 강의를 먼저 하고, 문장마다 GenAm TTS 모범 발음을 붙인 뒤 녹음으로 틀린 위치 진단과 엄격한 점수를 낸다.

확정된 요구:
- 새 저장소 `mgjungdev/sisyphus-studio`에 만든다.
- Kokoro로 오디오를 미리 생성한다.
- 로그인·제출이 없다.
- **녹음은 어떤 형태로도 저장하지 않는다.**
- 단어·음소 단위로 오류 위치를 표시하고, 점수를 후하게 주지 않는다.
- PC와 iOS Safari, 갤럭시(Samsung Internet·Chrome) 모두에서 잘 돌아가야 한다.
- 레슨 탭과 연습 탭을 나누고, 연습은 카드 형식으로 한다.
- **진행 방식: Lesson 02, 03만 먼저 옮겨 승인을 받은 뒤 나머지를 진행한다.**

## 진행 방식: 승인 관문 2개
| 단계 | 범위 | 소요 | 끝나면 |
|---|---|---|---|
| **파일럿 A** | 저장소, 배포, PWA. **Lesson 02·03만** 레슨 탭 + 연습 탭 카드 덱 + Kokoro 모범 발음 재생. 모바일과 PC 반응형 | 1.5–2일 | 배포 링크로 **승인 1** (내용, 화면, 카드, 음성 품질) |
| **파일럿 B** | 같은 두 레슨의 카드에 녹음 + 진단 + 엄격 채점. 음소 모델 경량화, 보정 테스트, 3종 기기 확인 | 7–10일 | **승인 2** (진단 정확도, 엄격성, 모바일 속도) |
| 확장 | 나머지 Lesson 01, 04–16, 참고 3편, 이어서 Vocabulary Studio 23일치. 엔진은 그대로 쓰고 내용 변환과 TTS 생성만 반복 | 3–5일 | 레슨 묶음마다 배포 링크 공유 |

- 채점 엔진은 레슨 수와 관계없이 한 번 만들면 된다. 그래서 파일럿 B가 전체 작업의 대부분이고, 확장 단계는 가볍다.
- 승인 전에는 다음 단계로 넘어가지 않는다. 피드백은 Lesson 02·03에서 고친 뒤 확장 단계에 일괄 반영한다.

## 재사용할 것
- `C:\Users\mingo\sisyphus\reading_lessons_pdf\src\lesson02.md`, `lesson03.md`: 이미 추출된 원문. Notion에서 다시 받아 최신본과 대조한다.
- `reading_lessons_pdf\build\img\`: 레슨 이미지. 서명 URL이 만료되므로 저장소에 복사한다.
- `library/site/css/tokens.css`, `base.css`, `site/sw.js`, `manifest.webmanifest`: 디자인 토큰과 PWA 패턴.
- `library/.github/workflows/pages.yml`: Pages 배포 패턴.

## 아키텍처
```
content/reading/lesson02.md, lesson03.md     ← 파일럿 범위
content/img/
tools/build.py      md → site/data/*.json (섹션·표·카드 항목 + 기대 음소열)
tools/tts.py        Kokoro → site/audio/<lesson>/<id>.<voice>.m4a  (--check 포함)
tools/variants.py   보정용 오답 음성 생성
tests/score.test.js 채점 회귀 테스트 (node + onnxruntime-node)
tests/perf.mjs      모바일 에뮬레이션 + CPU 스로틀 성능 측정
site/ index.html · js/(router, lesson, deck, player, recorder, worker/score.js) · css/ · data/ · audio/ · models/ · sw.js
```
- **카드 항목**: `{id, deck, plain, marked, words[{text, phones[], syllables, stress}], tune}`.
  - 박자와 강세는 강세 표시본에서 얻는다.
  - 음소열은 Kokoro와 같은 G2P(misaki/espeak, GenAm)로 만든다.
- **TTS**: 여 `af_heart`, 남 `am_michael`. 속도 1.0과 0.8. AAC(.m4a) 48kbps로 굽는다(iOS·삼성·PC 공통 재생). 레슨 단위로 지연 로드하고, 문장 해시로 캐시해 수정된 문장만 다시 생성한다.
- **내용 정리** (CLAUDE.md의 메타 텍스트 금지): "No audio recordings are embedded", "Source connection", 출처·교사용 문구는 사이트에 넣지 않는다.

## 화면: 레슨 탭과 연습 탭
URL은 `#/reading/02/lesson`과 `#/reading/02/practice`.
- **레슨 탭** (읽기 전용):
  - 들어가는 것: 목표, 설명, 그림, 대비표, 박자 드릴, 🇰🇷 팁, Check yourself.
  - 표의 단어를 탭하면 모범 발음을 재생한다. 녹음은 없다.
  - 좁은 화면에서는 4열 표를 행 단위 카드로 바꾼다.
- **연습 탭** (카드 덱):
  - 덱 순서: 단어 대비 → Warm-up → PRACTICE A–D → Short reading(문장 단위).
  - 카드 한 장 = 항목 하나.
    - 앞면: 평문, ▶ 모범(남/여, 느리게), ● 녹음.
    - 녹음 후: 진단, 점수, 박자 줄이 카드 위에 펼쳐진다.
    - "강세 보기" 버튼으로 표시본을 연다.
    - 대비 카드(pin/spin 등)는 한 장에 두 단어를 놓고 A–B–A 순서로 녹음한다.
  - 넘기기: 모바일은 스와이프와 하단 고정 바, PC는 ←/→ 키와 Space(재생), R(녹음).
  - 진행 표시(3/8, 통과 표시)는 저장하지 않는다.
- 공통: 모바일 우선. 터치 영역 44px 이상, 다크 모드, iOS safe-area.

## 녹음·채점 (파일럿 B)
- **저장 없음**: PCM은 Worker 메모리에서 채점에만 쓰고 바로 비운다. 파일, 다운로드, 서버 전송, 브라우저 저장소, 점수 이력이 모두 없다.
- **녹음**: getUserMedia + AudioWorklet로 PCM을 받아 16k로 리샘플링한다. 탭 한 번으로 시작하고, 그 탭 안에서 `AudioContext.resume()`(iOS 제약). 마이크의 AGC·소음 제거는 끄도록 요청하고, 기기가 무시해도 버티도록 화자 내 정규화를 한다.
- **추론**: Web Worker 안의 onnxruntime-web. 기본은 WASM SIMD, WebGPU는 있을 때만 쓴다(삼성·구형 iOS 대비). 멀티스레드 WASM은 coi-serviceworker로 켜고, 안 되면 단일 스레드로 폴백한다.
- **예산**: 모델 int8 50MB 이하. 채점은 중급 폰 3초 이하, PC 1초 이하. 메모리 피크 400MB 이하.
- **오류 위치 엔진**:
  1. 음소 CTC 모델: 공개 wav2vec2-base 음소 모델을 int4나 레이어 축소로 50MB 이하로 줄인다. 실패하면 DistilHuBERT급 모델을 TIMIT/LibriSpeech와 L2-ARCTIC(한국인 화자)으로 미세조정한다(약 25MB).
  2. 강제 정렬 + GOP로 음소별 점수를 낸다.
  3. 자유 인식과 편집거리 정렬로 대치/삽입(으)/누락을 분류한다.
  4. 강의 맞춤 측정기:
     - VOT: pin과 spin의 기식
     - 모음 길이: bet/bed
     - 탄설음 t
     - 박자 수와 강세 위치
     - 억양 방향 ↘↗
  5. 표시: 단어 밑줄을 정확/의심/오류로 칠하고, 탭하면 음소 칩과 "이렇게 들렸어요 / 이래야 해요" 설명, 모범 음성의 해당 구간 재생이 나온다.
- **엄격 채점**:
  - 가중 기하평균에 최악 단어로 상한을 둔다. 오류가 하나라도 있으면 90점 미만이다.
  - "의심"은 오류로 판정한다. 모든 단어가 정확일 때만 통과다.
  - Whisper와 MFCC 유사도는 점수에서 제외한다.
  - 보정 목표:
    - 모범 음성 ≈ 95점
    - Kokoro 오답 변형(`desku`, `suh-top`, `copy`, 평평한 억양) ≤ 60점, 위치 적중 ≥ 85%
    - 무음·다른 문장 ≤ 20점
    - 기기 간 차이 ±5점 이내
- 대안: 모바일 예산을 못 맞추면 Azure Pronunciation Assessment(유료 키 + 프록시)로 간다. 이때는 사용자에게 먼저 확인한다.

## 에이전트와 비용 검토
이전 안의 맞춤 에이전트 5개와 병렬 변환은 **파일럿 규모에서는 비용이 오히려 더 든다**.
- **비용이 드는 이유**:
  - 서브에이전트는 띄울 때마다 시스템 프롬프트, 도구 정의, 작업 맥락을 새로 읽는다.
  - 결과를 메인 세션에 다시 요약해 전달한다.
  - 같은 파일을 메인과 서브가 중복해서 읽는다.
  - 한 번에 수만 토큰씩 고정 비용이 붙고, 메인 세션의 캐시 이점도 잃는다.
- **에이전트가 비용 대비 유리한 경우**: 서로 독립적이고 큰 작업을 동시에 돌려 시간을 줄일 때다(예: 레슨 14개 동시 변환). 그때도 총 토큰은 줄지 않고 시간만 준다.
- **조정안**:
  - **파일럿 A·B: 맞춤 에이전트 0개.** 메인 세션이 직접 한다.
  - 정해진 일은 에이전트가 아니라 **스크립트**로 만든다. 한 번 만들면 반복 실행 비용이 거의 없다.
    - TTS 생성·검사: `tools/tts.py --check`
    - 채점 회귀: `tests/score.test.js`
    - 성능 측정: `tests/perf.mjs`
  - **확장 단계**: 레슨 14개와 Day 23개 변환은 build.py가 대부분 자동으로 처리하므로 기본은 메인 세션이 순차로 한다. 시간을 줄이고 싶을 때만 `general-purpose` 2–3개로 나누되, 그 전에 비용을 다시 확인받는다.
  - 기존 `Explore`·`Plan`은 막히는 조사가 생길 때만 1회씩 쓴다.

## 검증
- 파일럿 A:
  - `python tools/build.py`: Lesson 02·03 카드 수가 Notion `<details>` 수와 대비표 행 수에 맞는지 확인한다.
  - `python tools/tts.py --check`
  - 배포 후 iPhone Safari, 갤럭시 Samsung Internet·Chrome, PC에서 레슨 탭 재생과 연습 카드 넘기기·재생을 확인한다(사용자).
- 파일럿 B:
  - `node tests/score.test.js`: 보정 목표를 모두 통과하는지 확인한다.
  - `node tests/perf.mjs`: 4× CPU 스로틀에서 3초와 400MB 예산을 지키는지 확인한다.
  - 실기기에서 PRACTICE C 덱(spin/stop/sky)을 녹음·진단해 보고, 카드를 넘긴 뒤 녹음이 남지 않는지 확인한다.
- 배포 후 딥링크 `https://mgjungdev.github.io/sisyphus-studio/#/reading/02/practice`를 확인한다.

## 웨이브 (control center 프로젝트 `studio`)
- 단계 목록은 `docs/steps.json`, 피더는 `tools/pipeline.py`, 기록은 `docs/LOG.md`.
- 웨이브는 A 파일럿 A → B 파일럿 B → C 나머지 발음 레슨 순서다. 각 웨이브는 사용자 확인 단계(`*-OK`)로 끝난다.
- Vocabulary Studio는 2026-10-09 사용자 요청으로 지금 목록에서 뺐다. 나중에 따로 웨이브를 추가한다.
- 맞춤 에이전트는 두지 않는다. 각 단계가 새 세션 하나이고, 반복 작업은 스크립트로 한다.
