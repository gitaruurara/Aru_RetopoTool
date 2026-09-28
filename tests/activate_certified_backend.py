from pathlib import Path
for name in ('native_backend.py','viewport_session.py'):
 p=Path(name);s=p.read_text();assert 'aru_retopo_mesh_buffer_numeric.mll' in s
 p.write_text(s.replace('aru_retopo_mesh_buffer_numeric.mll','aru_retopo_mesh_buffer_certified.mll'))
p=Path('README.md');s=p.read_text()
old='500パッチ・約5万ポリゴンのMaya 2027検証では、ポイントドラッグ約28ms、リラックス約41ms（中央値、描画込み）です。実際の編集ハンドラーをスクリプトで実行した計測で、物理マウス操作の遅延とは異なります。60fpsは未達で、接続変更による再構築にも待ち時間があります。実機の操作感を確認しながら改善中です。'
new='参照面への投影では、前回の投影先が引き続き最寄りだと判定できるときに三角形探索を省略します。判定できない場合は通常の探索を行います。通常起動はこの処理を含む `aru_retopo_mesh_buffer_certified.mll` を使います。再ビルドは `cpp/build_interactive.ps1 -MayaVersion 2024`（または `2027`）で行えます。\n\n500パッチ・46,528面のMaya 2027比較では、同じ入力・カメラ・1600×1000表示で、リラックスが従来の約58〜60msから約43〜44ms、ポイントドラッグが約29.5msから約27.1msになりました（中央値、描画込み、最初のブラシは443 EPに作用）。実際の編集ハンドラーをスクリプトで実行した計測で、物理マウス操作の遅延とは異なります。60fpsは未達です。「最前面表示」OFFではガイドが通常のPython描画に戻り、表示負荷が増えます。'
assert old in s;s=s.replace(old,new);p.write_text(s)
