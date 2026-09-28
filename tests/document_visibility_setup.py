from pathlib import Path
p=Path('README.md');s=p.read_text(encoding='utf-8')
s=s.replace('約43〜44ms、ポイントドラッグが約29.5msから約27.1ms','約39〜40ms、ポイントドラッグが約29.5msから約27.1ms')
needle='再ビルドは `cpp/build_interactive.ps1 -MayaVersion 2024`（または `2027`）で行えます。'
s=s.replace(needle,needle+' ブラシの表裏・遮蔽判定はメインスレッド上のC++一括呼び出しを使い、法線以外の不要な付着情報を生成しません。専用DLLの再ビルドは `cpp/build_maya_visibility.ps1 -MayaVersion 2024`（または `2027`）です。DLLを使えない場合は従来の判定へ戻ります。')
p.write_text(s,encoding='utf-8')
p=Path('tests/visibility_candidate.py');s=p.read_text();needle='    source=textwrap.dedent(inspect.getsource(original))';s=s.replace(needle,needle+"\n    if 'from .maya_visibility import native_many' in source:raise RuntimeError('Already integrated; run visibility_release_cases.py instead.')");p.write_text(s)
p=Path('cpp/build_maya_visibility.ps1');s=p.read_text().replace('Maya projector build failed','Maya visibility build failed');p.write_text(s)
