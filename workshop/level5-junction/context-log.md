# Context log — 2026-10-05 下班前

## 目標
Four Crossings（my_jev.py）拿最高分，並找出 Jev 真正有用的角色。使用者要求：先從第一性原理充分研究，策略確認後才一次改 my_jev.py。

## 目前狀態
- my_jev.py = v5（hybrid、TIE_MARGIN 0.5），備份在 research/my_jev.v5.py。研究結束前不改。
- 已知分數（tick ~270）：
  - v4 rule 約 488（517.4 / 477.8 / 468.8）
  - v4 hybrid −811 / −78 / 499
  - v4 jev 約 −520
  - v5 hybrid 約 −681
- 第一性原理研究 workflow：run ID wf_e8251206-a3b
  - script：~/.claude/projects/-Users-untionglim-projects-jev-work-workshop-level5-junction/37ba1b1e-9f11-4930-b535-e2eb29c3a1ab/workflows/scripts/jev-first-principles-wf_1b585a2e-208.js
  - 結果：同目錄 subagents/workflows/wf_e8251206-a3b/journal.jsonl
  - 進度：Model、Analyze 已完成；Verify 剩 1 個 agent 在跑很慢的穩健性檢驗；Synthesize 尚未開始。
- 中間產物（sim.py、best_policy.py 等）已從 /tmp 備份到 research/fp/。/tmp 重開機會被清掉。

## 明天接續
1. `claude --continue`
2. 看 workflow 有沒有跑完：讀 journal.jsonl 最後的 synthesize 結果。
3. 如果中斷：用 `Workflow({scriptPath, resumeFromRunId: "wf_e8251206-a3b"})` 接續。
   - 若 /tmp/.../scratchpad/fp 已消失，先把 research/fp 複製回去。
4. 用 zh-TW 向使用者報告策略，取得同意後才一次改 my_jev.py，再實際跑 3 輪驗證。

## 更新：workflow 已結束（睡眠中斷）
- 6/8 agent 完成；slow verify（parallel[1]）stall 失敗；synthesize 因睡眠失敗。
- 接續：縮小 verify 樣本後，用 resumeFromRunId wf_e8251206-a3b 重跑（前面的結果會從快取取回）。
