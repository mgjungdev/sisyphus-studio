## Git Bash에서 qa.py 해시 인자 경로 변환
- 증상: `qa.py --shot "#/"` 결과 파일명이 `C:-Program Files-Git-...png`, 엉뚱한 페이지가 찍힘
- 원인: MSYS가 `/`로 시작하는 인자를 Windows 경로로 바꿈(`#/` → `C:/Program Files/Git/`)
- 대처: Bash에서는 `MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe tools/qa.py ...` 로 실행(또는 PowerShell 사용)
- 발생: 1회, 마지막 2026-10-09 (job #A-04)

## Playwright 전체 페이지 스크린샷 높이 초과
- 증상: `Cannot take screenshot larger than 32767 pixels on any dimension`
- 원인: 레슨 페이지가 모바일에서 3만 px 이상
- 대처: full_page=True에 clip={x,y,width,height}로 구간만 찍기(요소 위치는 page.evaluate로 구함)
- 발생: 1회, 마지막 2026-10-09 (job #A-04)

## 모바일 에뮬레이션에서 고정 하단 바가 화면 밖으로 밀림
- 증상: Playwright click 타임아웃 `<main id="view"> intercepts pointer events`, 고정 바 y가 innerHeight보다 큼
- 원인: 옆으로 날아가는 카드(transform)가 문서를 가로로 넓혀 모바일 브라우저가 축소 → 레이아웃 뷰포트가 바뀜
- 대처: 움직이는 요소의 부모에 `overflow-x: hidden; overflow-x: clip;`(음수 margin+padding으로 그림자 여유 확보)
- 발생: 1회, 마지막 2026-10-09 (job #A-05)

## Playwright WebKit 오프라인·미디어 테스트가 서비스 워커를 못 거침
- 증상: `set_offline(True)` 뒤 캐시된 파일도 `TypeError: Load failed`; 오프라인 `<audio>`가 readyState 0으로 멈춤
- 원인: WebKit의 set_offline은 서비스 워커 응답까지 막음. Windows WebKit은 미디어를 Media Foundation(UA `WMFSDK`)으로 직접 받아 서비스 워커를 거치지 않음
- 대처: 오프라인은 로컬 서버를 shutdown해서 만든다(`qa.py --pwa`가 그렇게 함). WebKit `<audio>` 오프라인 재생은 판정에서 빼고 fetch로 Range(206) 응답만 확인, 재생 판정은 chromium에서
- 발생: 1회, 마지막 2026-10-09 (job #A-06)

## Python 패치 스크립트로 파일을 고치면 CRLF·NUL이 섞임
- 증상: `SyntaxError: source code cannot contain null bytes`, 파일 전체가 CRLF로 바뀜
- 원인: Windows에서 `Path.write_text`가 \n을 \r\n으로 바꿈; Bash 히어독 안 Python 문자열의 `\0`·`\n`이 실제 NUL·줄바꿈으로 들어감
- 대처: 코드 수정은 Edit 도구로. 스크립트로 쓸 때는 `write_bytes(s.encode())` 또는 `write_text(..., newline="\n")`, 이스케이프가 필요한 문자열은 `bytes(1)`처럼 피해서 쓴다
- 발생: 1회, 마지막 2026-10-09 (job #A-06)
