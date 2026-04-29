## Summary

<!-- Describe what changed and why. Link related issues when relevant. -->

## Area

- [ ] Source connector or source quality
- [ ] Evidence contract or cited Q&A
- [ ] Embedding, rerank, or report generation
- [ ] Backfill, checkpointing, or long-task runner
- [ ] Deployment or server profile
- [ ] UI reuse
- [ ] Documentation
- [ ] Other:

## Verification

- [ ] `python -m pytest tests\vectordbz_v2 -q`
- [ ] `git diff --check`
- [ ] Secret scan over tracked files
- [ ] Manual smoke/health check if runtime behavior changed

## Safety

- [ ] No provider tokens, PATs, passwords, cookies, SSH material, or real `.env` files
- [ ] No generated archives, caches, screenshots, vector stores, or `node_modules`
- [ ] New LLM-facing behavior preserves deterministic evidence before narration
- [ ] New server behavior is environment-configured, not hardcoded to a local machine

## Notes

<!-- Add deployment notes, screenshots, or follow-up work if useful. -->
