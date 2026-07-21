---
name: hazop-risk-draft
description: 업로드 Excel의 Node, 변수, Guideword와 근거 데이터를 바탕으로 #3 위험성평가 초안을 작성할 때 적용한다.
---

# HAZOP 위험성평가 초안 작성 절차

1. `#2 가이드워드`의 각 Row를 독립 평가 단위로 본다.
2. Node, 변수, Guideword는 입력값 그대로 사용한다.
3. Workflow가 최초 조회한 MSDS 요약, 사고이력, 표준 HAZOP, 사용자 비고를 근거로 확인한다.
4. 초안 작성 중 물질 정보가 부족할 때만 MSDS 상세 조회 Tool을 추가 호출한다.
5. 사고이력이 부족하면 사고이력 Tool을 호출한다. 표준 HAZOP은 Workflow가 한 번 선조회한 Context만 재사용한다.
6. 일탈, 원인, 결과, 현재 안전조치를 한국어로 작성한다.
7. 빈도는 1~5 후보만 작성한다.
8. 강도는 1~4 후보만 작성한다.
9. 위험도는 계산하지 말고 `risk_score=0`, `risk_level="계산 전"`, `action_required="계산 전"`으로 둔다.
10. 판단근거, 빈도근거, 강도근거를 반드시 작성한다.

금지:

- 새 Node 생성 금지
- 새 변수 생성 금지
- 새 Guideword 생성 금지
- 근거 없는 단정 금지
