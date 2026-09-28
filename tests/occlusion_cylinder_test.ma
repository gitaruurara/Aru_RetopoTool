//Maya ASCII 2027 scene
//Name: occlusion_cylinder_test.ma
//Last modified: Fri, Sep 18, 2026 11:25:00 AM
//Codeset: 932
requires maya "2027";
requires -nodeType "aruRetopoMeshBuffer" "aru_retopo_mesh_buffer_certificates" "0.1.0";
requires -nodeType "aruRetopoPlan" "aru_retopo_plan_plugin.py" "0.1.0";
requires -nodeType "retopoGuideNode" "aru_retopo_guide_plugin.py" "1.0";
requires -nodeType "UsdDefaultSettings" -dataType "pxrUsdStageData" "mayaUsdPlugin" "0.37.0";
requires -nodeType "aruRetopoOverlay" "aru_retopo_draw_plugin.py" "0.1.0";
requires -nodeType "aruRetopoMesh" "aru_retopo_plugin.py" "0.1.0";
currentUnit -l centimeter -a degree -t film;
fileInfo "application" "maya";
fileInfo "product" "Maya 2027";
fileInfo "version" "2027";
fileInfo "cutIdentifier" "202607171511-52c21617ee";
fileInfo "osv" "Windows 11 Pro v2009 (Build: 26200)";
fileInfo "UUID" "1EC30433-436C-3A41-A023-0F9494E192D0";
createNode transform -s -n "persp";
	rename -uid "A9D4D0E0-404A-0538-C674-B4A0F876783F";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 10 6 12 ;
	setAttr ".r" -type "double3" -21 40 0 ;
createNode camera -s -n "perspShape" -p "persp";
	rename -uid "8AF89BA7-4148-5CCE-CD39-A0983A33DC88";
	setAttr -k off ".v" no;
	setAttr ".fl" 34.999999999999993;
	setAttr ".coi" 44.82186966202994;
	setAttr ".ow" 12;
	setAttr ".imn" -type "string" "persp";
	setAttr ".den" -type "string" "persp_depth";
	setAttr ".man" -type "string" "persp_mask";
	setAttr ".hc" -type "string" "viewSet -p %camera";
createNode transform -s -n "top";
	rename -uid "CE951EC8-4EFC-5A02-85AC-1F861B249596";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 0 1000.1 0 ;
	setAttr ".r" -type "double3" -90 0 0 ;
createNode camera -s -n "topShape" -p "top";
	rename -uid "92C82704-4AAA-6332-24AE-44A3C8E89956";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "top";
	setAttr ".den" -type "string" "top_depth";
	setAttr ".man" -type "string" "top_mask";
	setAttr ".hc" -type "string" "viewSet -t %camera";
	setAttr ".o" yes;
createNode transform -s -n "front";
	rename -uid "718BDF3C-4F2D-EBDB-F021-1BBDCA3B06A3";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 0 0 1000.1 ;
createNode camera -s -n "frontShape" -p "front";
	rename -uid "98EA3065-4D9E-DB77-5632-879B4CE702CD";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "front";
	setAttr ".den" -type "string" "front_depth";
	setAttr ".man" -type "string" "front_mask";
	setAttr ".hc" -type "string" "viewSet -f %camera";
	setAttr ".o" yes;
createNode transform -s -n "side";
	rename -uid "D489B80C-4D21-C08C-8644-26A468BFB402";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 1000.1 0 0 ;
	setAttr ".r" -type "double3" 0 90 0 ;
createNode camera -s -n "sideShape" -p "side";
	rename -uid "1CB583C6-4D20-0683-3091-37AAA8B12F01";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "side";
	setAttr ".den" -type "string" "side_depth";
	setAttr ".man" -type "string" "side_mask";
	setAttr ".hc" -type "string" "viewSet -s %camera";
	setAttr ".o" yes;
createNode transform -n "occlusionCylinder";
	rename -uid "5D13B97C-4B2F-FC21-2734-F9B1F426FF89";
createNode mesh -n "occlusionCylinderShape" -p "occlusionCylinder";
	rename -uid "0F515A31-4BAF-C85D-4715-C4AAECFF4F1B";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr -s 10 ".gtag";
	setAttr ".gtag[0].gtagnm" -type "string" "bottom";
	setAttr ".gtag[0].gtagcmp" -type "componentList" 1 "f[64:127]";
	setAttr ".gtag[1].gtagnm" -type "string" "bottomRing";
	setAttr ".gtag[1].gtagcmp" -type "componentList" 1 "e[0:63]";
	setAttr ".gtag[2].gtagnm" -type "string" "cylBottomCap";
	setAttr ".gtag[2].gtagcmp" -type "componentList" 2 "vtx[0:63]" "vtx[128]";
	setAttr ".gtag[3].gtagnm" -type "string" "cylBottomRing";
	setAttr ".gtag[3].gtagcmp" -type "componentList" 1 "vtx[0:63]";
	setAttr ".gtag[4].gtagnm" -type "string" "cylSides";
	setAttr ".gtag[4].gtagcmp" -type "componentList" 1 "vtx[0:127]";
	setAttr ".gtag[5].gtagnm" -type "string" "cylTopCap";
	setAttr ".gtag[5].gtagcmp" -type "componentList" 2 "vtx[64:127]" "vtx[129]";
	setAttr ".gtag[6].gtagnm" -type "string" "cylTopRing";
	setAttr ".gtag[6].gtagcmp" -type "componentList" 1 "vtx[64:127]";
	setAttr ".gtag[7].gtagnm" -type "string" "sides";
	setAttr ".gtag[7].gtagcmp" -type "componentList" 1 "f[0:63]";
	setAttr ".gtag[8].gtagnm" -type "string" "top";
	setAttr ".gtag[8].gtagcmp" -type "componentList" 1 "f[128:191]";
	setAttr ".gtag[9].gtagnm" -type "string" "topRing";
	setAttr ".gtag[9].gtagcmp" -type "componentList" 1 "e[64:127]";
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr -s 260 ".uvst[0].uvsp";
	setAttr ".uvst[0].uvsp[0:249]" -type "float2" 0.9994719 0.11274791 0.99227214
		 0.10061376 0.98034978 0.088714465 0.96381927 0.07716462 0.94284022 0.066075474 0.91761446
		 0.055553779 0.88838482 0.045700893 0.85543311 0.036611706 0.8190763 0.028373748 0.77966487
		 0.021066353 0.73757815 0.014759898 0.69322151 0.0095151067 0.64702213 0.005382508
		 0.59942496 0.0024018884 0.55088842 0.00060194731 0.50187981 2.9802322e-08 0.45287126
		 0.00060194731 0.40433466 0.0024018586 0.35673749 0.0053824782 0.31053817 0.0095150769
		 0.26618147 0.014759853 0.22409475 0.021066308 0.1846832 0.028373703 0.14832646 0.036611661
		 0.11537462 0.045700848 0.086145043 0.055553719 0.060919195 0.0660754 0.039940059
		 0.077164561 0.023409665 0.088714406 0.011487186 0.1006137 0.0042874515 0.11274783
		 0.0018798113 0.12499997 0.0042874217 0.13725212 0.011487126 0.14938626 0.023409605
		 0.16128555 0.03994 0.17283541 0.060919106 0.18392456 0.086144924 0.19444627 0.11537451
		 0.20429915 0.14832634 0.21338832 0.18468305 0.22162628 0.22409457 0.22893369 0.26618135
		 0.23524013 0.31053793 0.24048492 0.35673738 0.24461752 0.40433455 0.24759814 0.45287108
		 0.24939808 0.50187963 0.25 0.55088824 0.24939808 0.59942484 0.24759814 0.64702201
		 0.24461752 0.69322133 0.24048492 0.73757803 0.23524016 0.77966475 0.22893369 0.8190763
		 0.22162631 0.85543299 0.21338835 0.88838482 0.20429915 0.91761446 0.19444627 0.94284034
		 0.18392459 0.9638195 0.17283544 0.98034978 0.16128558 0.99227238 0.14938629 0.99947202
		 0.13725215 1.0018796921 0.125 0 0.25 0.015625 0.25 0.03125 0.25 0.046875 0.25 0.0625
		 0.25 0.078125 0.25 0.09375 0.25 0.109375 0.25 0.125 0.25 0.140625 0.25 0.15625 0.25
		 0.171875 0.25 0.1875 0.25 0.203125 0.25 0.21875 0.25 0.234375 0.25 0.25 0.25 0.265625
		 0.25 0.28125 0.25 0.296875 0.25 0.3125 0.25 0.328125 0.25 0.34375 0.25 0.359375 0.25
		 0.375 0.25 0.390625 0.25 0.40625 0.25 0.421875 0.25 0.4375 0.25 0.453125 0.25 0.46875
		 0.25 0.484375 0.25 0.5 0.25 0.515625 0.25 0.53125 0.25 0.546875 0.25 0.5625 0.25
		 0.578125 0.25 0.59375 0.25 0.609375 0.25 0.625 0.25 0.640625 0.25 0.65625 0.25 0.671875
		 0.25 0.6875 0.25 0.703125 0.25 0.71875 0.25 0.734375 0.25 0.75 0.25 0.765625 0.25
		 0.78125 0.25 0.796875 0.25 0.8125 0.25 0.828125 0.25 0.84375 0.25 0.859375 0.25 0.875
		 0.25 0.890625 0.25 0.90625 0.25 0.921875 0.25 0.9375 0.25 0.953125 0.25 0.96875 0.25
		 0.984375 0.25 1 0.25 0 0.75 0.015625 0.75 0.03125 0.75 0.046875 0.75 0.0625 0.75
		 0.078125 0.75 0.09375 0.75 0.109375 0.75 0.125 0.75 0.140625 0.75 0.15625 0.75 0.171875
		 0.75 0.1875 0.75 0.203125 0.75 0.21875 0.75 0.234375 0.75 0.25 0.75 0.265625 0.75
		 0.28125 0.75 0.296875 0.75 0.3125 0.75 0.328125 0.75 0.34375 0.75 0.359375 0.75 0.375
		 0.75 0.390625 0.75 0.40625 0.75 0.421875 0.75 0.4375 0.75 0.453125 0.75 0.46875 0.75
		 0.484375 0.75 0.5 0.75 0.515625 0.75 0.53125 0.75 0.546875 0.75 0.5625 0.75 0.578125
		 0.75 0.59375 0.75 0.609375 0.75 0.625 0.75 0.640625 0.75 0.65625 0.75 0.671875 0.75
		 0.6875 0.75 0.703125 0.75 0.71875 0.75 0.734375 0.75 0.75 0.75 0.765625 0.75 0.78125
		 0.75 0.796875 0.75 0.8125 0.75 0.828125 0.75 0.84375 0.75 0.859375 0.75 0.875 0.75
		 0.890625 0.75 0.90625 0.75 0.921875 0.75 0.9375 0.75 0.953125 0.75 0.96875 0.75 0.984375
		 0.75 1 0.75 0.9994719 0.86274791 0.99227214 0.85061377 0.98034978 0.83871448 0.96381927
		 0.82716465 0.94284022 0.81607544 0.91761446 0.80555379 0.88838482 0.79570091 0.85543311
		 0.78661168 0.8190763 0.77837372 0.77966487 0.77106637 0.73757815 0.7647599 0.69322151
		 0.75951511 0.64702213 0.75538254 0.59942496 0.75240189 0.55088842 0.75060195 0.50187981
		 0.75 0.45287126 0.75060195 0.40433466 0.75240183 0.35673749 0.75538248 0.31053817
		 0.75951505 0.26618147 0.76475984 0.22409475 0.77106631 0.1846832 0.77837372 0.14832646
		 0.78661168 0.11537462 0.79570085 0.086145043 0.80555373 0.060919195 0.81607538 0.039940059
		 0.82716453 0.023409665 0.83871442 0.011487186 0.85061371 0.0042874515 0.86274785
		 0.0018798113 0.875 0.0042874217 0.88725209 0.011487126 0.89938629 0.023409605 0.91128552
		 0.03994 0.92283541 0.060919106 0.93392456 0.086144924 0.94444627 0.11537451 0.95429915
		 0.14832634 0.96338832 0.18468305 0.97162628 0.22409457 0.97893369 0.26618135 0.9852401
		 0.31053793 0.99048495 0.35673738 0.99461752 0.40433455 0.99759817 0.45287108 0.99939811
		 0.50187963 1 0.55088824 0.99939811 0.59942484 0.99759817 0.64702201 0.99461752 0.69322133
		 0.99048495 0.73757803 0.98524016 0.77966475 0.97893369 0.8190763 0.97162628 0.85543299
		 0.96338832;
	setAttr ".uvst[0].uvsp[250:259]" 0.88838482 0.95429915 0.91761446 0.94444627
		 0.94284034 0.93392456 0.9638195 0.92283547 0.98034978 0.91128558 0.99227238 0.89938629
		 0.99947202 0.88725215 1.0018796921 0.875 0.50187969 0.125 0.50187969 0.875;
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Ambient+Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr -s 130 ".vt[0:129]"  2.98555303 -3 -0.29405034 2.94235492 -3 -0.58526981
		 2.87082005 -3 -0.87085271 2.77163792 -3 -1.14804888 2.64576316 -3 -1.41418886 2.49440837 -3 -1.6667093
		 2.31903124 -3 -1.90317857 2.12132025 -3 -2.12131906 1.90318 -3 -2.31903005 1.66671109 -3 -2.49440765
		 1.41419053 -3 -2.64576268 1.14805079 -3 -2.77163744 0.87085462 -3 -2.87081981 0.58527166 -3 -2.94235492
		 0.29405218 -3 -2.98555326 8.4936619e-07 -3 -2.99999905 -0.29405051 -3 -2.9855535
		 -0.58526999 -3 -2.94235516 -0.87085301 -3 -2.87082052 -1.14804935 -3 -2.77163815
		 -1.4141891 -3 -2.6457634 -1.66670966 -3 -2.49440861 -1.90317893 -3 -2.31903124 -2.12131929 -3 -2.12132025
		 -2.31903028 -3 -1.90317988 -2.49440789 -3 -1.66671073 -2.64576292 -3 -1.41419029
		 -2.77163792 -3 -1.14805055 -2.87082005 -3 -0.87085438 -2.94235516 -3 -0.58527136
		 -2.9855535 -3 -0.29405189 -2.99999928 -3 -5.364418e-07 -2.98555374 -3 0.29405084
		 -2.94235539 -3 0.58527035 -2.87082052 -3 0.87085336 -2.77163815 -3 1.14804959 -2.6457634 -3 1.41418958
		 -2.49440861 -3 1.66671002 -2.31903124 -3 1.90317929 -2.12132025 -3 2.12131977 -1.90317988 -3 2.31903076
		 -1.66671073 -3 2.49440813 -1.41419029 -3 2.6457634 -1.14805031 -3 2.77163815 -0.87085408 -3 2.87082052
		 -0.58527106 -3 2.94235539 -0.29405159 -3 2.98555374 -2.0116568e-07 -3 2.99999952
		 0.29405117 -3 2.98555374 0.5852707 -3 2.94235563 0.87085372 -3 2.87082076 1.14805007 -3 2.77163839
		 1.41418982 -3 2.64576364 1.66671038 -3 2.49440885 1.90317965 -3 2.31903124 2.12132025 -3 2.12132025
		 2.31903124 -3 1.90317988 2.49440861 -3 1.66671073 2.64576364 -3 1.41419029 2.77163839 -3 1.14805031
		 2.870821 -3 0.87085408 2.94235563 -3 0.585271 2.98555422 -3 0.29405141 3 -3 0 2.98555303 3 -0.29405034
		 2.94235492 3 -0.58526981 2.87082005 3 -0.87085271 2.77163792 3 -1.14804888 2.64576316 3 -1.41418886
		 2.49440837 3 -1.6667093 2.31903124 3 -1.90317857 2.12132025 3 -2.12131906 1.90318 3 -2.31903005
		 1.66671109 3 -2.49440765 1.41419053 3 -2.64576268 1.14805079 3 -2.77163744 0.87085462 3 -2.87081981
		 0.58527166 3 -2.94235492 0.29405218 3 -2.98555326 8.4936619e-07 3 -2.99999905 -0.29405051 3 -2.9855535
		 -0.58526999 3 -2.94235516 -0.87085301 3 -2.87082052 -1.14804935 3 -2.77163815 -1.4141891 3 -2.6457634
		 -1.66670966 3 -2.49440861 -1.90317893 3 -2.31903124 -2.12131929 3 -2.12132025 -2.31903028 3 -1.90317988
		 -2.49440789 3 -1.66671073 -2.64576292 3 -1.41419029 -2.77163792 3 -1.14805055 -2.87082005 3 -0.87085438
		 -2.94235516 3 -0.58527136 -2.9855535 3 -0.29405189 -2.99999928 3 -5.364418e-07 -2.98555374 3 0.29405084
		 -2.94235539 3 0.58527035 -2.87082052 3 0.87085336 -2.77163815 3 1.14804959 -2.6457634 3 1.41418958
		 -2.49440861 3 1.66671002 -2.31903124 3 1.90317929 -2.12132025 3 2.12131977 -1.90317988 3 2.31903076
		 -1.66671073 3 2.49440813 -1.41419029 3 2.6457634 -1.14805031 3 2.77163815 -0.87085408 3 2.87082052
		 -0.58527106 3 2.94235539 -0.29405159 3 2.98555374 -2.0116568e-07 3 2.99999952 0.29405117 3 2.98555374
		 0.5852707 3 2.94235563 0.87085372 3 2.87082076 1.14805007 3 2.77163839 1.41418982 3 2.64576364
		 1.66671038 3 2.49440885 1.90317965 3 2.31903124 2.12132025 3 2.12132025 2.31903124 3 1.90317988
		 2.49440861 3 1.66671073 2.64576364 3 1.41419029 2.77163839 3 1.14805031 2.870821 3 0.87085408
		 2.94235563 3 0.585271 2.98555422 3 0.29405141 3 3 0 0 -3 0 0 3 0;
	setAttr -s 320 ".ed";
	setAttr ".ed[0:165]"  0 1 0 1 2 0 2 3 0 3 4 0 4 5 0 5 6 0 6 7 0 7 8 0 8 9 0
		 9 10 0 10 11 0 11 12 0 12 13 0 13 14 0 14 15 0 15 16 0 16 17 0 17 18 0 18 19 0 19 20 0
		 20 21 0 21 22 0 22 23 0 23 24 0 24 25 0 25 26 0 26 27 0 27 28 0 28 29 0 29 30 0 30 31 0
		 31 32 0 32 33 0 33 34 0 34 35 0 35 36 0 36 37 0 37 38 0 38 39 0 39 40 0 40 41 0 41 42 0
		 42 43 0 43 44 0 44 45 0 45 46 0 46 47 0 47 48 0 48 49 0 49 50 0 50 51 0 51 52 0 52 53 0
		 53 54 0 54 55 0 55 56 0 56 57 0 57 58 0 58 59 0 59 60 0 60 61 0 61 62 0 62 63 0 63 0 0
		 64 65 0 65 66 0 66 67 0 67 68 0 68 69 0 69 70 0 70 71 0 71 72 0 72 73 0 73 74 0 74 75 0
		 75 76 0 76 77 0 77 78 0 78 79 0 79 80 0 80 81 0 81 82 0 82 83 0 83 84 0 84 85 0 85 86 0
		 86 87 0 87 88 0 88 89 0 89 90 0 90 91 0 91 92 0 92 93 0 93 94 0 94 95 0 95 96 0 96 97 0
		 97 98 0 98 99 0 99 100 0 100 101 0 101 102 0 102 103 0 103 104 0 104 105 0 105 106 0
		 106 107 0 107 108 0 108 109 0 109 110 0 110 111 0 111 112 0 112 113 0 113 114 0 114 115 0
		 115 116 0 116 117 0 117 118 0 118 119 0 119 120 0 120 121 0 121 122 0 122 123 0 123 124 0
		 124 125 0 125 126 0 126 127 0 127 64 0 0 64 1 1 65 1 2 66 1 3 67 1 4 68 1 5 69 1
		 6 70 1 7 71 1 8 72 1 9 73 1 10 74 1 11 75 1 12 76 1 13 77 1 14 78 1 15 79 1 16 80 1
		 17 81 1 18 82 1 19 83 1 20 84 1 21 85 1 22 86 1 23 87 1 24 88 1 25 89 1 26 90 1 27 91 1
		 28 92 1 29 93 1 30 94 1 31 95 1 32 96 1 33 97 1 34 98 1 35 99 1 36 100 1 37 101 1;
	setAttr ".ed[166:319]" 38 102 1 39 103 1 40 104 1 41 105 1 42 106 1 43 107 1
		 44 108 1 45 109 1 46 110 1 47 111 1 48 112 1 49 113 1 50 114 1 51 115 1 52 116 1
		 53 117 1 54 118 1 55 119 1 56 120 1 57 121 1 58 122 1 59 123 1 60 124 1 61 125 1
		 62 126 1 63 127 1 128 0 1 128 1 1 128 2 1 128 3 1 128 4 1 128 5 1 128 6 1 128 7 1
		 128 8 1 128 9 1 128 10 1 128 11 1 128 12 1 128 13 1 128 14 1 128 15 1 128 16 1 128 17 1
		 128 18 1 128 19 1 128 20 1 128 21 1 128 22 1 128 23 1 128 24 1 128 25 1 128 26 1
		 128 27 1 128 28 1 128 29 1 128 30 1 128 31 1 128 32 1 128 33 1 128 34 1 128 35 1
		 128 36 1 128 37 1 128 38 1 128 39 1 128 40 1 128 41 1 128 42 1 128 43 1 128 44 1
		 128 45 1 128 46 1 128 47 1 128 48 1 128 49 1 128 50 1 128 51 1 128 52 1 128 53 1
		 128 54 1 128 55 1 128 56 1 128 57 1 128 58 1 128 59 1 128 60 1 128 61 1 128 62 1
		 128 63 1 64 129 1 65 129 1 66 129 1 67 129 1 68 129 1 69 129 1 70 129 1 71 129 1
		 72 129 1 73 129 1 74 129 1 75 129 1 76 129 1 77 129 1 78 129 1 79 129 1 80 129 1
		 81 129 1 82 129 1 83 129 1 84 129 1 85 129 1 86 129 1 87 129 1 88 129 1 89 129 1
		 90 129 1 91 129 1 92 129 1 93 129 1 94 129 1 95 129 1 96 129 1 97 129 1 98 129 1
		 99 129 1 100 129 1 101 129 1 102 129 1 103 129 1 104 129 1 105 129 1 106 129 1 107 129 1
		 108 129 1 109 129 1 110 129 1 111 129 1 112 129 1 113 129 1 114 129 1 115 129 1 116 129 1
		 117 129 1 118 129 1 119 129 1 120 129 1 121 129 1 122 129 1 123 129 1 124 129 1 125 129 1
		 126 129 1 127 129 1;
	setAttr -s 192 -ch 640 ".fc[0:191]" -type "polyFaces" 
		f 4 0 129 -65 -129
		mu 0 4 64 65 130 129
		f 4 1 130 -66 -130
		mu 0 4 65 66 131 130
		f 4 2 131 -67 -131
		mu 0 4 66 67 132 131
		f 4 3 132 -68 -132
		mu 0 4 67 68 133 132
		f 4 4 133 -69 -133
		mu 0 4 68 69 134 133
		f 4 5 134 -70 -134
		mu 0 4 69 70 135 134
		f 4 6 135 -71 -135
		mu 0 4 70 71 136 135
		f 4 7 136 -72 -136
		mu 0 4 71 72 137 136
		f 4 8 137 -73 -137
		mu 0 4 72 73 138 137
		f 4 9 138 -74 -138
		mu 0 4 73 74 139 138
		f 4 10 139 -75 -139
		mu 0 4 74 75 140 139
		f 4 11 140 -76 -140
		mu 0 4 75 76 141 140
		f 4 12 141 -77 -141
		mu 0 4 76 77 142 141
		f 4 13 142 -78 -142
		mu 0 4 77 78 143 142
		f 4 14 143 -79 -143
		mu 0 4 78 79 144 143
		f 4 15 144 -80 -144
		mu 0 4 79 80 145 144
		f 4 16 145 -81 -145
		mu 0 4 80 81 146 145
		f 4 17 146 -82 -146
		mu 0 4 81 82 147 146
		f 4 18 147 -83 -147
		mu 0 4 82 83 148 147
		f 4 19 148 -84 -148
		mu 0 4 83 84 149 148
		f 4 20 149 -85 -149
		mu 0 4 84 85 150 149
		f 4 21 150 -86 -150
		mu 0 4 85 86 151 150
		f 4 22 151 -87 -151
		mu 0 4 86 87 152 151
		f 4 23 152 -88 -152
		mu 0 4 87 88 153 152
		f 4 24 153 -89 -153
		mu 0 4 88 89 154 153
		f 4 25 154 -90 -154
		mu 0 4 89 90 155 154
		f 4 26 155 -91 -155
		mu 0 4 90 91 156 155
		f 4 27 156 -92 -156
		mu 0 4 91 92 157 156
		f 4 28 157 -93 -157
		mu 0 4 92 93 158 157
		f 4 29 158 -94 -158
		mu 0 4 93 94 159 158
		f 4 30 159 -95 -159
		mu 0 4 94 95 160 159
		f 4 31 160 -96 -160
		mu 0 4 95 96 161 160
		f 4 32 161 -97 -161
		mu 0 4 96 97 162 161
		f 4 33 162 -98 -162
		mu 0 4 97 98 163 162
		f 4 34 163 -99 -163
		mu 0 4 98 99 164 163
		f 4 35 164 -100 -164
		mu 0 4 99 100 165 164
		f 4 36 165 -101 -165
		mu 0 4 100 101 166 165
		f 4 37 166 -102 -166
		mu 0 4 101 102 167 166
		f 4 38 167 -103 -167
		mu 0 4 102 103 168 167
		f 4 39 168 -104 -168
		mu 0 4 103 104 169 168
		f 4 40 169 -105 -169
		mu 0 4 104 105 170 169
		f 4 41 170 -106 -170
		mu 0 4 105 106 171 170
		f 4 42 171 -107 -171
		mu 0 4 106 107 172 171
		f 4 43 172 -108 -172
		mu 0 4 107 108 173 172
		f 4 44 173 -109 -173
		mu 0 4 108 109 174 173
		f 4 45 174 -110 -174
		mu 0 4 109 110 175 174
		f 4 46 175 -111 -175
		mu 0 4 110 111 176 175
		f 4 47 176 -112 -176
		mu 0 4 111 112 177 176
		f 4 48 177 -113 -177
		mu 0 4 112 113 178 177
		f 4 49 178 -114 -178
		mu 0 4 113 114 179 178
		f 4 50 179 -115 -179
		mu 0 4 114 115 180 179
		f 4 51 180 -116 -180
		mu 0 4 115 116 181 180
		f 4 52 181 -117 -181
		mu 0 4 116 117 182 181
		f 4 53 182 -118 -182
		mu 0 4 117 118 183 182
		f 4 54 183 -119 -183
		mu 0 4 118 119 184 183
		f 4 55 184 -120 -184
		mu 0 4 119 120 185 184
		f 4 56 185 -121 -185
		mu 0 4 120 121 186 185
		f 4 57 186 -122 -186
		mu 0 4 121 122 187 186
		f 4 58 187 -123 -187
		mu 0 4 122 123 188 187
		f 4 59 188 -124 -188
		mu 0 4 123 124 189 188
		f 4 60 189 -125 -189
		mu 0 4 124 125 190 189
		f 4 61 190 -126 -190
		mu 0 4 125 126 191 190
		f 4 62 191 -127 -191
		mu 0 4 126 127 192 191
		f 4 63 128 -128 -192
		mu 0 4 127 128 193 192
		f 3 -1 -193 193
		mu 0 3 1 0 258
		f 3 -2 -194 194
		mu 0 3 2 1 258
		f 3 -3 -195 195
		mu 0 3 3 2 258
		f 3 -4 -196 196
		mu 0 3 4 3 258
		f 3 -5 -197 197
		mu 0 3 5 4 258
		f 3 -6 -198 198
		mu 0 3 6 5 258
		f 3 -7 -199 199
		mu 0 3 7 6 258
		f 3 -8 -200 200
		mu 0 3 8 7 258
		f 3 -9 -201 201
		mu 0 3 9 8 258
		f 3 -10 -202 202
		mu 0 3 10 9 258
		f 3 -11 -203 203
		mu 0 3 11 10 258
		f 3 -12 -204 204
		mu 0 3 12 11 258
		f 3 -13 -205 205
		mu 0 3 13 12 258
		f 3 -14 -206 206
		mu 0 3 14 13 258
		f 3 -15 -207 207
		mu 0 3 15 14 258
		f 3 -16 -208 208
		mu 0 3 16 15 258
		f 3 -17 -209 209
		mu 0 3 17 16 258
		f 3 -18 -210 210
		mu 0 3 18 17 258
		f 3 -19 -211 211
		mu 0 3 19 18 258
		f 3 -20 -212 212
		mu 0 3 20 19 258
		f 3 -21 -213 213
		mu 0 3 21 20 258
		f 3 -22 -214 214
		mu 0 3 22 21 258
		f 3 -23 -215 215
		mu 0 3 23 22 258
		f 3 -24 -216 216
		mu 0 3 24 23 258
		f 3 -25 -217 217
		mu 0 3 25 24 258
		f 3 -26 -218 218
		mu 0 3 26 25 258
		f 3 -27 -219 219
		mu 0 3 27 26 258
		f 3 -28 -220 220
		mu 0 3 28 27 258
		f 3 -29 -221 221
		mu 0 3 29 28 258
		f 3 -30 -222 222
		mu 0 3 30 29 258
		f 3 -31 -223 223
		mu 0 3 31 30 258
		f 3 -32 -224 224
		mu 0 3 32 31 258
		f 3 -33 -225 225
		mu 0 3 33 32 258
		f 3 -34 -226 226
		mu 0 3 34 33 258
		f 3 -35 -227 227
		mu 0 3 35 34 258
		f 3 -36 -228 228
		mu 0 3 36 35 258
		f 3 -37 -229 229
		mu 0 3 37 36 258
		f 3 -38 -230 230
		mu 0 3 38 37 258
		f 3 -39 -231 231
		mu 0 3 39 38 258
		f 3 -40 -232 232
		mu 0 3 40 39 258
		f 3 -41 -233 233
		mu 0 3 41 40 258
		f 3 -42 -234 234
		mu 0 3 42 41 258
		f 3 -43 -235 235
		mu 0 3 43 42 258
		f 3 -44 -236 236
		mu 0 3 44 43 258
		f 3 -45 -237 237
		mu 0 3 45 44 258
		f 3 -46 -238 238
		mu 0 3 46 45 258
		f 3 -47 -239 239
		mu 0 3 47 46 258
		f 3 -48 -240 240
		mu 0 3 48 47 258
		f 3 -49 -241 241
		mu 0 3 49 48 258
		f 3 -50 -242 242
		mu 0 3 50 49 258
		f 3 -51 -243 243
		mu 0 3 51 50 258
		f 3 -52 -244 244
		mu 0 3 52 51 258
		f 3 -53 -245 245
		mu 0 3 53 52 258
		f 3 -54 -246 246
		mu 0 3 54 53 258
		f 3 -55 -247 247
		mu 0 3 55 54 258
		f 3 -56 -248 248
		mu 0 3 56 55 258
		f 3 -57 -249 249
		mu 0 3 57 56 258
		f 3 -58 -250 250
		mu 0 3 58 57 258
		f 3 -59 -251 251
		mu 0 3 59 58 258
		f 3 -60 -252 252
		mu 0 3 60 59 258
		f 3 -61 -253 253
		mu 0 3 61 60 258
		f 3 -62 -254 254
		mu 0 3 62 61 258
		f 3 -63 -255 255
		mu 0 3 63 62 258
		f 3 -64 -256 192
		mu 0 3 0 63 258
		f 3 64 257 -257
		mu 0 3 256 255 259
		f 3 65 258 -258
		mu 0 3 255 254 259
		f 3 66 259 -259
		mu 0 3 254 253 259
		f 3 67 260 -260
		mu 0 3 253 252 259
		f 3 68 261 -261
		mu 0 3 252 251 259
		f 3 69 262 -262
		mu 0 3 251 250 259
		f 3 70 263 -263
		mu 0 3 250 249 259
		f 3 71 264 -264
		mu 0 3 249 248 259
		f 3 72 265 -265
		mu 0 3 248 247 259
		f 3 73 266 -266
		mu 0 3 247 246 259
		f 3 74 267 -267
		mu 0 3 246 245 259
		f 3 75 268 -268
		mu 0 3 245 244 259
		f 3 76 269 -269
		mu 0 3 244 243 259
		f 3 77 270 -270
		mu 0 3 243 242 259
		f 3 78 271 -271
		mu 0 3 242 241 259
		f 3 79 272 -272
		mu 0 3 241 240 259
		f 3 80 273 -273
		mu 0 3 240 239 259
		f 3 81 274 -274
		mu 0 3 239 238 259
		f 3 82 275 -275
		mu 0 3 238 237 259
		f 3 83 276 -276
		mu 0 3 237 236 259
		f 3 84 277 -277
		mu 0 3 236 235 259
		f 3 85 278 -278
		mu 0 3 235 234 259
		f 3 86 279 -279
		mu 0 3 234 233 259
		f 3 87 280 -280
		mu 0 3 233 232 259
		f 3 88 281 -281
		mu 0 3 232 231 259
		f 3 89 282 -282
		mu 0 3 231 230 259
		f 3 90 283 -283
		mu 0 3 230 229 259
		f 3 91 284 -284
		mu 0 3 229 228 259
		f 3 92 285 -285
		mu 0 3 228 227 259
		f 3 93 286 -286
		mu 0 3 227 226 259
		f 3 94 287 -287
		mu 0 3 226 225 259
		f 3 95 288 -288
		mu 0 3 225 224 259
		f 3 96 289 -289
		mu 0 3 224 223 259
		f 3 97 290 -290
		mu 0 3 223 222 259
		f 3 98 291 -291
		mu 0 3 222 221 259
		f 3 99 292 -292
		mu 0 3 221 220 259
		f 3 100 293 -293
		mu 0 3 220 219 259
		f 3 101 294 -294
		mu 0 3 219 218 259
		f 3 102 295 -295
		mu 0 3 218 217 259
		f 3 103 296 -296
		mu 0 3 217 216 259
		f 3 104 297 -297
		mu 0 3 216 215 259
		f 3 105 298 -298
		mu 0 3 215 214 259
		f 3 106 299 -299
		mu 0 3 214 213 259
		f 3 107 300 -300
		mu 0 3 213 212 259
		f 3 108 301 -301
		mu 0 3 212 211 259
		f 3 109 302 -302
		mu 0 3 211 210 259
		f 3 110 303 -303
		mu 0 3 210 209 259
		f 3 111 304 -304
		mu 0 3 209 208 259
		f 3 112 305 -305
		mu 0 3 208 207 259
		f 3 113 306 -306
		mu 0 3 207 206 259
		f 3 114 307 -307
		mu 0 3 206 205 259
		f 3 115 308 -308
		mu 0 3 205 204 259
		f 3 116 309 -309
		mu 0 3 204 203 259
		f 3 117 310 -310
		mu 0 3 203 202 259
		f 3 118 311 -311
		mu 0 3 202 201 259
		f 3 119 312 -312
		mu 0 3 201 200 259
		f 3 120 313 -313
		mu 0 3 200 199 259
		f 3 121 314 -314
		mu 0 3 199 198 259
		f 3 122 315 -315
		mu 0 3 198 197 259
		f 3 123 316 -316
		mu 0 3 197 196 259
		f 3 124 317 -317
		mu 0 3 196 195 259
		f 3 125 318 -318
		mu 0 3 195 194 259
		f 3 126 319 -319
		mu 0 3 194 257 259
		f 3 127 256 -320
		mu 0 3 257 256 259;
	setAttr ".cd" -type "dataPolyComponent" Index_Data Edge 0 ;
	setAttr ".cvd" -type "dataPolyComponent" Index_Data Vertex 0 ;
	setAttr ".pd[0]" -type "dataPolyComponent" Index_Data UV 0 ;
	setAttr ".hfd" -type "dataPolyComponent" Index_Data Face 0 ;
createNode transform -n "aruRetopoGuide1";
	rename -uid "BDA0A49C-4B45-18E6-4695-1EA2D116FEA4";
createNode retopoGuideNode -n "aruRetopoGuideShape1" -p "aruRetopoGuide1";
	rename -uid "8EECDB5D-4402-F15C-24CA-96AD9F5D6273";
	setAttr -k off ".v";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".nd" -type "string" (
		"{\"version\":1,\"positions\":[[3.0,-2.0,0.0],[2.121320343559643,-2.0,2.121320343559643],[1.8369701987210297e-16,-2.0,3.0],[-2.1213203435596424,-2.0,2.121320343559643],[-3.0,-2.0,3.6739403974420594e-16],[-2.121320343559643,-2.0,-2.1213203435596424],[-5.51091059616309e-16,-2.0,-3.0],[2.121320343559642,-2.0,-2.121320343559643],[3.0,0.0,0.0],[2.121320343559643,0.0,2.121320343559643],[1.8369701987210297e-16,0.0,3.0],[-2.1213203435596424,0.0,2.121320343559643],[-3.0,0.0,3.6739403974420594e-16],[-2.121320343559643,0.0,-2.1213203435596424],[-5.51091059616309e-16,0.0,-3.0],[2.121320343559642,0.0,-2.121320343559643],[3.0,2.0,0.0],[2.121320343559643,2.0,2.121320343559643],[1.8369701987210297e-16,2.0,3.0],[-2.1213203435596424,2.0,2.121320343559643],[-3.0,2.0,3.6739403974420594e-16],[-2.121320343559643,2.0,-2.1213203435596424],[-5.51091059616309e-16,2.0,-3.0],[2.121320343559642,2.0,-2.121320343559643],[3.0,-2.0,0.795649469518632],[2.683929478903747,-2.0,1.5587112082155388],[1.5587112082155388,-2.0,2.683929478903747],[0.7956494695186322,-2.0,3.0],[-0.7956494695186318,-2.0,3.0],[-1.5587112082155383,-2.0,2.683929478903747],[-2.6839294789037464,-2.0,1.5587112082155388],[-3.0,-2.0,0.7956494695186324],[-3.0,-2.0,-0.7956494695186317],[-2.683929478903747,-2.0,-1.5587112082155383],[-1.5587112082155388,-2.0,-2.6839294789037464],[-0.7956494695186326,-2.0,-3.0],[0.7956494695186315,-2.0,-3.0],[1.5587112082155379,-2.0,-2.683929478903747],[2.683929478903746,-2.0,-1.558711208215539],[3.0,-2.0,-0.795649469518632],[3.0,0.0,0.795649469518632],[2.683929478903747,0.0,1.5587112082155388],[1.5587112082155388,0.0,2.683929478903747],[0.7956494695186322,0.0,3.0],[-0.7956494695186318,0.0,3.0],[-1.5587112082155383,0.0,2.683929478903747],[-2.6839294789037464,0.0,1.5587112082155388],[-3.0,0.0,0.7956494695186324],[-3.0,0.0,-0.7956494695186317],[-2.683929478903747,0.0,-1.5587112082155383],[-1.5587112082155388,0.0,-2.6839294789037464],[-0.7956494695186326,0.0,-3.0],[0.7956494695186315,0.0,-3.0],[1.5587112082155379,0.0,-2.683929478903747],[2.683929478903746,0.0,-1.558711208215539],[3.0,0.0,-0.795649469518632],[3.0,2.0,0.795649469518632],[2.683929478903747,2.0,1.5587112082155388],[1.5587112082155388,2.0,2.683929478903747],[0.7956494695186322,2.0,3.0],[-0.7956494695186318,2.0,3.0],[-1.5587112082155383,2.0,2.683929478903747],[-2.6839294789037464,2.0,1.5587112082155388],[-3.0,2.0,0.7956494695186324],[-3.0,2.0,-0.7956494695186317],[-2.683929478903747,2.0,-1.5587112082155383],[-1.5587112082155388,2.0,-2.6839294789037464],[-0.7956494695186326,2.0,-3.0],[0.7956494695186315,2.0,-3.0],[1.5587112082155379,2.0,-2.683929478903747],[2.683929478903746,2.0,-1.558711208215539],[3.0,2.0,-0.795649469518632],[3.0,-1.3333333333333333,0.0],[3.0,-0.6666666666666666,0.0],[2.121320343559643,-1.3333333333333333,2.121320343559643],[2.121320343559643,-0.6666666666666666,2.121320343559643],[1.83697019872103e-16,-1.3333333333333333,3.0],[1.83697019872103e-16,-0.6666666666666666,3.0],[-2.1213203435596424,-1.3333333333333333,2.121320343559643],[-2.1213203435596424,-0.6666666666666666,2.121320343559643],[-3.0,-1.3333333333333333,3.67394039744206e-16],[-3.0,-0.6666666666666666,3.67394039744206e-16],[-2.121320343559643,-1.3333333333333333,-2.1213203435596424],[-2.121320343559643,-0.6666666666666666,-2.1213203435596424],[-5.51091059616309e-16,-1.3333333333333333,-3.0],[-5.51091059616309e-16,-0.6666666666666666,-3.0],[2.121320343559642,-1.3333333333333333,-2.121320343559643],[2.121320343559642,-0.6666666666666666,-2.121320343559643],[3.0,0.6666666666666666,0.0],[3.0,1.3333333333333333,0.0],[2.121320343559643,0.6666666666666666,2.121320343559643],[2.121320343559643,1.3333333333333333,2.121320343559643],[1.83697019872103e-16,0.6666666666666666,3.0],[1.83697019872103e-16,1.3333333333333333,3.0],[-2.1213203435596424,0.6666666666666666,2.121320343559643],[-2.1213203435596424,1.3333333333333333,2.121320343559643],[-3.0,0.6666666666666666,3.67394039744206e-16],[-3.0,1.3333333333333333,3.67394039744206e-16],[-2.121320343559643,0.6666666666666666,-2.1213203435596424],[-2.121320343559643,1.3333333333333333,-2.1213203435596424],[-5.51091059616309e-16,0.6666666666666666,-3.0],[-5.51091059616309e-16,1.3333333333333333,-3.0],[2.121320343559642,0.6666666666666666,-2.121320343559643],[2.121320343559642,1.3333333333333333,-2.121320343559643]],\"surface_binding\":[null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null],\"splines\":[[0,24,25,1],[1,26,27,2],[2,28,29,3],[3,30,31,4],[4,32,33,5],[5,34,35,6],[6,36,37,7],[7,38,39,0],[8,40,41,9],[9,42,43,10],[10,44,45,11],[11,46,47,12],[12,48,49,13],[13,50,51,14],[14,52,53,15],[15,54,55,8],[16,56,57,17],[17,58,59,18],[18,60,61,19],[19,62,63,20],[20,64,65,21],[21,66,67,22],[22,68,69,23],[23,70,71,16],[0,72,73,8],[1,74,75,9],[2,76,77,10],[3,78,79,11],[4,80,81,12],[5,82,83,13],[6,84,85,14],[7,86,87,15],[8,88,89,16],[9,90,91,17],[10,92,93,18],[11,94,95,19],[12,96,97,20],[13,98,99,21],[14,100,101,22],[15,102,103,23]],\"standalone_eps\":[],\"manual_handles\":[]}");
	setAttr ".mn" -type "string" "|occlusionCylinder|occlusionCylinderShape";
createNode transform -n "aruRetopoMesh1";
	rename -uid "5EF07BF9-48CF-E235-A659-83B55E74A172";
	setAttr -l on -k off ".tx";
	setAttr -l on -k off ".ty";
	setAttr -l on -k off ".tz";
	setAttr -l on -k off ".rx";
	setAttr -l on -k off ".ry";
	setAttr -l on -k off ".rz";
	setAttr -l on -k off ".sx";
	setAttr -l on -k off ".sy";
	setAttr -l on -k off ".sz";
	setAttr -l on ".it" no;
createNode mesh -n "aruRetopoMesh1Shape" -p "aruRetopoMesh1";
	rename -uid "C4CBABD9-4094-DE86-8E96-079E93B16D92";
	setAttr -k off ".v";
	setAttr ".ove" yes;
	setAttr ".ovc" 17;
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Ambient+Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
createNode aruRetopoOverlay -n "aruRetopoOverlayShape1" -p "aruRetopoMesh1";
	rename -uid "58E227E4-4202-1685-7688-10A9D421535B";
	setAttr -k off ".v";
createNode lightLinker -s -n "lightLinker1";
	rename -uid "98B75335-4A76-E740-46A3-B3A0F1CFE254";
	setAttr -s 3 ".lnk";
	setAttr -s 3 ".slnk";
createNode UsdDefaultSettings -n "UsdDefaultRenderSettings";
	rename -uid "058A7D46-4004-0B22-09F7-9EBB5D841B52";
	setAttr ".srl" -type "string" "#usda 1.0\n(\n    renderSettingsPrimPath = \"/Render/SceneRenderSettings\"\n)\n\ndef Scope \"Render\"\n{\n    def RenderSettings \"SceneRenderSettings\"\n    {\n        custom string adskUsd:externalCamera = \"|persp\" (\n            displayName = \"External Camera\"\n        )\n        rel products = </Render/BeautyProduct>\n    }\n\n    def RenderVar \"color\"\n    {\n        uniform string sourceName = \"color\"\n    }\n\n    def RenderProduct \"BeautyProduct\"\n    {\n        rel orderedVars = </Render/color>\n        token productName = \"./default.png\"\n    }\n}\n\n";
	setAttr ".ssl" -type "string" "#usda 1.0\n\n";
	setAttr ".asp" -type "string" "UsdDefaultRenderSettings,/Render/SceneRenderSettings";
lockNode -l 1 ;
createNode displayLayerManager -n "layerManager";
	rename -uid "8921D6B5-4FA6-6A5A-A35D-CEB1994F8117";
createNode displayLayer -n "defaultLayer";
	rename -uid "EBF3D4DE-4644-F957-3DE6-1CB9DD5EC8A9";
	setAttr ".ufem" -type "stringArray" 0  ;
createNode renderLayerManager -n "renderLayerManager";
	rename -uid "5068E4B5-461C-3AB0-938E-0180692D5E13";
createNode renderLayer -n "defaultRenderLayer";
	rename -uid "BF6143CF-400C-5113-1CD8-56B0AB4CAB41";
	setAttr ".g" yes;
createNode shapeEditorManager -n "shapeEditorManager";
	rename -uid "3559AD3A-4761-A82B-6EB8-FD9056C7AC04";
createNode poseInterpolatorManager -n "poseInterpolatorManager";
	rename -uid "26DF7408-4E13-1EDE-2DF0-3786C48891E2";
createNode aruRetopoMesh -n "aruRetopoGenerator1";
	rename -uid "7A068483-484F-5F8B-A4A7-7386430FD06A";
	addAttr -s false -ci true -sn "previewShadingGroup" -ln "previewShadingGroup" -at "message";
	addAttr -s false -ci true -sn "nativeBackend" -ln "nativeBackend" -at "message";
	addAttr -s false -ci true -sn "nativePlan" -ln "nativePlan" -at "message";
	setAttr ".sps" -type "string" "[\"[[0,-1],[24,1],[8,1],[25,-1]]\", \"[[1,-1],[25,1],[9,1],[26,-1]]\", \"[[2,-1],[26,1],[10,1],[27,-1]]\", \"[[3,-1],[27,1],[11,1],[28,-1]]\", \"[[4,-1],[28,1],[12,1],[29,-1]]\", \"[[5,-1],[29,1],[13,1],[30,-1]]\", \"[[6,-1],[30,1],[14,1],[31,-1]]\", \"[[7,-1],[31,1],[15,1],[24,-1]]\", \"[[8,-1],[32,1],[16,1],[33,-1]]\", \"[[9,-1],[33,1],[17,1],[34,-1]]\", \"[[10,-1],[34,1],[18,1],[35,-1]]\", \"[[11,-1],[35,1],[19,1],[36,-1]]\", \"[[12,-1],[36,1],[20,1],[37,-1]]\", \"[[13,-1],[37,1],[21,1],[38,-1]]\", \"[[14,-1],[38,1],[22,1],[39,-1]]\", \"[[15,-1],[39,1],[23,1],[32,-1]]\"]";
	setAttr ".ri" 2;
createNode lambert -n "aruRetopoPreviewMaterial1";
	rename -uid "B28E9C6D-4C0E-54A6-EEED-DBAF825A8BE4";
	setAttr ".c" -type "float3" 0.16 0.40000001 0.46000001 ;
createNode shadingEngine -n "aruRetopoPreviewSG1";
	rename -uid "C50304FF-4123-9A94-C549-E2B8411C0172";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo1";
	rename -uid "7B82941D-4A17-8F2A-B791-66B63DFCD326";
createNode aruRetopoPlan -n "aruRetopoPlan1";
	rename -uid "D5B00762-4FDD-1DEC-6290-2E85B1D53307";
createNode aruRetopoMeshBuffer -n "aruRetopoNative1";
	rename -uid "F2B597EF-4290-C096-075E-1AB8441D538C";
	addAttr -s false -ci true -sn "retopoOwner" -ln "retopoOwner" -at "message";
	setAttr ".pr" yes;
createNode script -n "uiConfigurationScriptNode";
	rename -uid "9B31CF53-4716-59D7-9402-AA9B6EE4307D";
	setAttr ".b" -type "string" (
		"// Maya Mel UI Configuration File.\n//\n//  This script is machine generated.  Edit at your own risk.\n//\n//\n\nglobal string $gMainPane;\nif (`paneLayout -exists $gMainPane`) {\n\n\tglobal int $gUseScenePanelConfig;\n\tint    $useSceneConfig = $gUseScenePanelConfig;\n\tint    $nodeEditorPanelVisible = stringArrayContains(\"nodeEditorPanel1\", `getPanel -vis`);\n\tint    $nodeEditorWorkspaceControlOpen = (`workspaceControl -exists nodeEditorPanel1Window` && `workspaceControl -q -visible nodeEditorPanel1Window`);\n\tint    $menusOkayInPanels = `optionVar -q allowMenusInPanels`;\n\tint    $nVisPanes = `paneLayout -q -nvp $gMainPane`;\n\tint    $nPanes = 0;\n\tstring $editorName;\n\tstring $panelName;\n\tstring $itemFilterName;\n\tstring $panelConfig;\n\n\t//\n\t//  get current state of the UI\n\t//\n\tsceneUIReplacement -update $gMainPane;\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Top View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Top View\")) -mbv $menusOkayInPanels  $panelName;\n"
		+ "\t\t$editorName = $panelName;\n        modelEditor -e \n            -camera \"|top\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n            -selectionHiliteDisplay 1\n            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n            -textureAnisotropic 0\n            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n"
		+ "            -depthOfFieldPreview 1\n            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n            -transpInShadows 0\n            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n            -interactiveDisableShadows 0\n            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n"
		+ "            -hulls 1\n            -grid 1\n            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n            -dynamicConstraints 1\n            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n            -excludeObjectPreset \"すべて\" \n            -shadows 0\n            -captureSequenceNumber -1\n            -width 1\n            -height 1\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"mayaUsdProxyShapeBaseDisplayFilter\" 1 \n"
		+ "            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Side View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Side View\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        modelEditor -e \n            -camera \"|side\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n            -selectionHiliteDisplay 1\n            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n"
		+ "            -textureAnisotropic 0\n            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n            -depthOfFieldPreview 1\n            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n            -transpInShadows 0\n            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n"
		+ "            -interactiveDisableShadows 0\n            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n            -hulls 1\n            -grid 1\n            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n            -dynamicConstraints 1\n            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n"
		+ "            -excludeObjectPreset \"すべて\" \n            -shadows 0\n            -captureSequenceNumber -1\n            -width 1\n            -height 1\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"mayaUsdProxyShapeBaseDisplayFilter\" 1 \n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Front View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Front View\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        modelEditor -e \n            -camera \"|front\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n"
		+ "            -selectionHiliteDisplay 1\n            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n            -textureAnisotropic 0\n            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n            -depthOfFieldPreview 1\n            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n"
		+ "            -transpInShadows 0\n            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n            -interactiveDisableShadows 0\n            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n            -hulls 1\n            -grid 1\n            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n"
		+ "            -dynamicConstraints 1\n            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n            -excludeObjectPreset \"すべて\" \n            -shadows 0\n            -captureSequenceNumber -1\n            -width 1\n            -height 1\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"mayaUsdProxyShapeBaseDisplayFilter\" 1 \n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Persp View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Persp View\")) -mbv $menusOkayInPanels  $panelName;\n"
		+ "\t\t$editorName = $panelName;\n        modelEditor -e \n            -camera \"|persp\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n            -selectionHiliteDisplay 1\n            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n            -textureAnisotropic 0\n            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n"
		+ "            -depthOfFieldPreview 1\n            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n            -transpInShadows 0\n            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n            -interactiveDisableShadows 0\n            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n"
		+ "            -hulls 1\n            -grid 0\n            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n            -dynamicConstraints 1\n            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n            -excludeObjectPreset \"すべて\" \n            -shadows 0\n            -captureSequenceNumber -1\n            -width 1600\n            -height 1000\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"mayaUsdProxyShapeBaseDisplayFilter\" 1 \n"
		+ "            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"outlinerPanel\" (localizedPanelLabel(\"ToggledOutliner\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\toutlinerPanel -edit -l (localizedPanelLabel(\"ToggledOutliner\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        outlinerEditor -e \n            -showShapes 0\n            -showAssignedMaterials 0\n            -showTimeEditor 1\n            -showReferenceNodes 1\n            -showReferenceMembers 1\n            -showAttributes 0\n            -showConnected 0\n            -showAnimCurvesOnly 0\n            -showMuteInfo 0\n            -organizeByLayer 1\n            -organizeByClip 1\n            -showAnimLayerWeight 1\n            -autoExpandLayers 1\n            -autoExpand 0\n            -showDagOnly 1\n            -showAssets 1\n            -showContainedOnly 1\n            -showPublishedAsConnected 0\n            -showParentContainers 0\n"
		+ "            -showContainerContents 1\n            -ignoreDagHierarchy 0\n            -expandConnections 0\n            -showUpstreamCurves 1\n            -showUnitlessCurves 1\n            -showCompounds 1\n            -showLeafs 1\n            -showNumericAttrsOnly 0\n            -highlightActive 1\n            -autoSelectNewObjects 0\n            -doNotSelectNewObjects 0\n            -dropIsParent 1\n            -transmitFilters 0\n            -setFilter \"defaultSetFilter\" \n            -showSetMembers 1\n            -allowMultiSelection 1\n            -alwaysToggleSelect 0\n            -directSelect 0\n            -isSet 0\n            -isSetMember 0\n            -showUfeItems 1\n            -displayMode \"DAG\" \n            -expandObjects 0\n            -setsIgnoreFilters 1\n            -containersIgnoreFilters 0\n            -editAttrName 0\n            -showAttrValues 0\n            -highlightSecondary 0\n            -showUVAttrsOnly 0\n            -showTextureNodesOnly 0\n            -attrAlphaOrder \"default\" \n            -animLayerFilterOptions \"allAffecting\" \n"
		+ "            -sortOrder \"none\" \n            -longNames 0\n            -niceNames 1\n            -showNamespace 1\n            -showPinIcons 0\n            -mapMotionTrails 0\n            -ignoreHiddenAttribute 0\n            -ignoreOutlinerColor 0\n            -renderFilterVisible 0\n            -renderFilterIndex 0\n            -selectionOrder \"chronological\" \n            -expandAttribute 0\n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"outlinerPanel\" (localizedPanelLabel(\"Outliner\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\toutlinerPanel -edit -l (localizedPanelLabel(\"Outliner\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        outlinerEditor -e \n            -showShapes 0\n            -showAssignedMaterials 0\n            -showTimeEditor 1\n            -showReferenceNodes 0\n            -showReferenceMembers 0\n            -showAttributes 0\n            -showConnected 0\n            -showAnimCurvesOnly 0\n"
		+ "            -showMuteInfo 0\n            -organizeByLayer 1\n            -organizeByClip 1\n            -showAnimLayerWeight 1\n            -autoExpandLayers 1\n            -autoExpand 0\n            -showDagOnly 1\n            -showAssets 1\n            -showContainedOnly 1\n            -showPublishedAsConnected 0\n            -showParentContainers 0\n            -showContainerContents 1\n            -ignoreDagHierarchy 0\n            -expandConnections 0\n            -showUpstreamCurves 1\n            -showUnitlessCurves 1\n            -showCompounds 1\n            -showLeafs 1\n            -showNumericAttrsOnly 0\n            -highlightActive 1\n            -autoSelectNewObjects 0\n            -doNotSelectNewObjects 0\n            -dropIsParent 1\n            -transmitFilters 0\n            -setFilter \"defaultSetFilter\" \n            -showSetMembers 1\n            -allowMultiSelection 1\n            -alwaysToggleSelect 0\n            -directSelect 0\n            -showUfeItems 1\n            -displayMode \"DAG\" \n            -expandObjects 0\n"
		+ "            -setsIgnoreFilters 1\n            -containersIgnoreFilters 0\n            -editAttrName 0\n            -showAttrValues 0\n            -highlightSecondary 0\n            -showUVAttrsOnly 0\n            -showTextureNodesOnly 0\n            -attrAlphaOrder \"default\" \n            -animLayerFilterOptions \"allAffecting\" \n            -sortOrder \"none\" \n            -longNames 0\n            -niceNames 1\n            -showNamespace 1\n            -showPinIcons 0\n            -mapMotionTrails 0\n            -ignoreHiddenAttribute 0\n            -ignoreOutlinerColor 0\n            -renderFilterVisible 0\n            -ufeFilter \"USD\" \"InactivePrims\" -ufeFilterValue 0\n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"graphEditor\" (localizedPanelLabel(\"Graph Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Graph Editor\")) -mbv $menusOkayInPanels  $panelName;\n"
		+ "\n\t\t\t$editorName = ($panelName+\"OutlineEd\");\n            outlinerEditor -e \n                -showShapes 1\n                -showAssignedMaterials 0\n                -showTimeEditor 1\n                -showReferenceNodes 0\n                -showReferenceMembers 0\n                -showAttributes 1\n                -showConnected 1\n                -showAnimCurvesOnly 1\n                -showMuteInfo 0\n                -organizeByLayer 1\n                -organizeByClip 1\n                -showAnimLayerWeight 1\n                -autoExpandLayers 1\n                -autoExpand 1\n                -showDagOnly 0\n                -showAssets 1\n                -showContainedOnly 0\n                -showPublishedAsConnected 0\n                -showParentContainers 0\n                -showContainerContents 0\n                -ignoreDagHierarchy 0\n                -expandConnections 1\n                -showUpstreamCurves 1\n                -showUnitlessCurves 1\n                -showCompounds 0\n                -showLeafs 1\n                -showNumericAttrsOnly 1\n"
		+ "                -highlightActive 0\n                -autoSelectNewObjects 1\n                -doNotSelectNewObjects 0\n                -dropIsParent 1\n                -transmitFilters 1\n                -setFilter \"0\" \n                -showSetMembers 0\n                -allowMultiSelection 1\n                -alwaysToggleSelect 0\n                -directSelect 0\n                -showUfeItems 1\n                -displayMode \"DAG\" \n                -expandObjects 0\n                -setsIgnoreFilters 1\n                -containersIgnoreFilters 0\n                -editAttrName 0\n                -showAttrValues 0\n                -highlightSecondary 0\n                -showUVAttrsOnly 0\n                -showTextureNodesOnly 0\n                -attrAlphaOrder \"default\" \n                -animLayerFilterOptions \"allAffecting\" \n                -sortOrder \"none\" \n                -longNames 0\n                -niceNames 1\n                -showNamespace 1\n                -showPinIcons 1\n                -mapMotionTrails 1\n                -ignoreHiddenAttribute 0\n"
		+ "                -ignoreOutlinerColor 0\n                -renderFilterVisible 0\n                $editorName;\n\n\t\t\t$editorName = ($panelName+\"GraphEd\");\n            animCurveEditor -e \n                -displayValues 0\n                -snapTime \"integer\" \n                -snapValue \"none\" \n                -showPlayRangeShades \"on\" \n                -lockPlayRangeShades \"off\" \n                -smoothness \"fine\" \n                -resultSamples 1\n                -resultScreenSamples 0\n                -resultUpdate \"delayed\" \n                -showUpstreamCurves 1\n                -showRowButtons 1\n                -tangentScale 1\n                -tangentLineThickness 1\n                -keyMinScale 1\n                -stackedCurvesMin -1\n                -stackedCurvesMax 1\n                -stackedCurvesSpace 0.2\n                -preSelectionHighlight 0\n                -limitToSelectedCurves 0\n                -constrainDrag 0\n                -valueLinesToggle 0\n                -outliner \"graphEditor1OutlineEd\" \n                -highlightAffectedCurves 0\n"
		+ "                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"dopeSheetPanel\" (localizedPanelLabel(\"Dope Sheet\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Dope Sheet\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = ($panelName+\"OutlineEd\");\n            outlinerEditor -e \n                -showShapes 1\n                -showAssignedMaterials 0\n                -showTimeEditor 1\n                -showReferenceNodes 0\n                -showReferenceMembers 0\n                -showAttributes 1\n                -showConnected 1\n                -showAnimCurvesOnly 1\n                -showMuteInfo 0\n                -organizeByLayer 1\n                -organizeByClip 1\n                -showAnimLayerWeight 1\n                -autoExpandLayers 1\n                -autoExpand 0\n                -showDagOnly 0\n                -showAssets 1\n                -showContainedOnly 0\n"
		+ "                -showPublishedAsConnected 0\n                -showParentContainers 0\n                -showContainerContents 0\n                -ignoreDagHierarchy 0\n                -expandConnections 1\n                -showUpstreamCurves 1\n                -showUnitlessCurves 0\n                -showCompounds 0\n                -showLeafs 1\n                -showNumericAttrsOnly 1\n                -highlightActive 0\n                -autoSelectNewObjects 0\n                -doNotSelectNewObjects 1\n                -dropIsParent 1\n                -transmitFilters 0\n                -setFilter \"0\" \n                -showSetMembers 1\n                -allowMultiSelection 1\n                -alwaysToggleSelect 0\n                -directSelect 0\n                -showUfeItems 1\n                -displayMode \"DAG\" \n                -expandObjects 0\n                -setsIgnoreFilters 1\n                -containersIgnoreFilters 0\n                -editAttrName 0\n                -showAttrValues 0\n                -highlightSecondary 0\n                -showUVAttrsOnly 0\n"
		+ "                -showTextureNodesOnly 0\n                -attrAlphaOrder \"default\" \n                -animLayerFilterOptions \"allAffecting\" \n                -sortOrder \"none\" \n                -longNames 0\n                -niceNames 1\n                -showNamespace 1\n                -showPinIcons 0\n                -mapMotionTrails 1\n                -ignoreHiddenAttribute 0\n                -ignoreOutlinerColor 0\n                -renderFilterVisible 0\n                $editorName;\n\n\t\t\t$editorName = ($panelName+\"DopeSheetEd\");\n            dopeSheetEditor -e \n                -displayValues 0\n                -snapTime \"none\" \n                -snapValue \"none\" \n                -outliner \"dopeSheetPanel1OutlineEd\" \n                -hierarchyBelow 0\n                -selectionWindow 0 0 0 0 \n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"timeEditorPanel\" (localizedPanelLabel(\"Time Editor\")) `;\n\tif (\"\" != $panelName) {\n"
		+ "\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Time Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"clipEditorPanel\" (localizedPanelLabel(\"Trax Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Trax Editor\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = clipEditorNameFromPanel($panelName);\n            clipEditor -e \n                -displayValues 0\n                -snapTime \"none\" \n                -snapValue \"none\" \n                -initialized 0\n                -manageSequencer 0 \n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"sequenceEditorPanel\" (localizedPanelLabel(\"Sequencer\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Sequencer\")) -mbv $menusOkayInPanels  $panelName;\n"
		+ "\n\t\t\t$editorName = sequenceEditorNameFromPanel($panelName);\n            cameraSequencer -e \n                -displayValues 0\n                -snapTime \"none\" \n                -snapValue \"none\" \n                -initialized 0\n                -showThumbnail 1\n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"hyperGraphPanel\" (localizedPanelLabel(\"Hypergraph Hierarchy\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Hypergraph Hierarchy\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = ($panelName+\"HyperGraphEd\");\n            hyperGraph -e \n                -graphLayoutStyle \"hierarchicalLayout\" \n                -orientation \"horiz\" \n                -mergeConnections 0\n                -zoom 1\n                -animateTransition 0\n                -showRelationships 1\n                -showShapes 0\n                -showDeformers 0\n                -showExpressions 0\n"
		+ "                -showConstraints 0\n                -showConnectionFromSelected 0\n                -showConnectionToSelected 0\n                -showConstraintLabels 0\n                -showUnderworld 0\n                -showInvisible 0\n                -showNamespace 1\n                -transitionFrames 1\n                -opaqueContainers 0\n                -freeform 0\n                -imagePosition 0 0 \n                -imageScale 1\n                -imageEnabled 0\n                -graphType \"DAG\" \n                -heatMapDisplay 0\n                -updateSelection 1\n                -updateNodeAdded 1\n                -useDrawOverrideColor 0\n                -limitGraphTraversal -1\n                -range 0 0 \n                -iconSize \"smallIcons\" \n                -showCachedConnections 0\n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"hyperShadePanel\" (localizedPanelLabel(\"Hypershade\")) `;\n\tif (\"\" != $panelName) {\n"
		+ "\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Hypershade\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"visorPanel\" (localizedPanelLabel(\"Visor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Visor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"nodeEditorPanel\" (localizedPanelLabel(\"Node Editor\")) `;\n\tif ($nodeEditorPanelVisible || $nodeEditorWorkspaceControlOpen) {\n\t\tif (\"\" == $panelName) {\n\t\t\tif ($useSceneConfig) {\n\t\t\t\t$panelName = `scriptedPanel -unParent  -type \"nodeEditorPanel\" -l (localizedPanelLabel(\"Node Editor\")) -mbv $menusOkayInPanels `;\n\n\t\t\t$editorName = ($panelName+\"NodeEditorEd\");\n            nodeEditor -e \n                -allAttributes 0\n                -allNodes 0\n"
		+ "                -autoSizeNodes 1\n                -consistentNameSize 1\n                -createNodeCommand \"nodeEdCreateNodeCommand\" \n                -connectNodeOnCreation 0\n                -connectOnDrop 0\n                -copyConnectionsOnPaste 0\n                -connectionStyle \"bezier\" \n                -defaultPinnedState 0\n                -additiveGraphingMode 0\n                -connectedGraphingMode 1\n                -settingsChangedCallback \"nodeEdSyncControls\" \n                -traversalDepthLimit -1\n                -keyPressCommand \"nodeEdKeyPressCommand\" \n                -nodeTitleMode \"name\" \n                -gridSnap 0\n                -gridVisibility 1\n                -crosshairOnEdgeDragging 0\n                -popupMenuScript \"nodeEdBuildPanelMenus\" \n                -showNamespace 1\n                -showShapes 1\n                -showSGShapes 0\n                -showTransforms 1\n                -useAssets 1\n                -syncedSelection 1\n                -extendToShapes 1\n                -showUnitConversions 0\n"
		+ "                -editorMode \"default\" \n                -hasWatchpoint 0\n                $editorName;\n\t\t\t}\n\t\t} else {\n\t\t\t$label = `panel -q -label $panelName`;\n\t\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Node Editor\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = ($panelName+\"NodeEditorEd\");\n            nodeEditor -e \n                -allAttributes 0\n                -allNodes 0\n                -autoSizeNodes 1\n                -consistentNameSize 1\n                -createNodeCommand \"nodeEdCreateNodeCommand\" \n                -connectNodeOnCreation 0\n                -connectOnDrop 0\n                -copyConnectionsOnPaste 0\n                -connectionStyle \"bezier\" \n                -defaultPinnedState 0\n                -additiveGraphingMode 0\n                -connectedGraphingMode 1\n                -settingsChangedCallback \"nodeEdSyncControls\" \n                -traversalDepthLimit -1\n                -keyPressCommand \"nodeEdKeyPressCommand\" \n                -nodeTitleMode \"name\" \n                -gridSnap 0\n"
		+ "                -gridVisibility 1\n                -crosshairOnEdgeDragging 0\n                -popupMenuScript \"nodeEdBuildPanelMenus\" \n                -showNamespace 1\n                -showShapes 1\n                -showSGShapes 0\n                -showTransforms 1\n                -useAssets 1\n                -syncedSelection 1\n                -extendToShapes 1\n                -showUnitConversions 0\n                -editorMode \"default\" \n                -hasWatchpoint 0\n                $editorName;\n\t\t\tif (!$useSceneConfig) {\n\t\t\t\tpanel -e -l $label $panelName;\n\t\t\t}\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"createNodePanel\" (localizedPanelLabel(\"Create Node\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Create Node\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"polyTexturePlacementPanel\" (localizedPanelLabel(\"UV Editor\")) `;\n"
		+ "\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"UV Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"renderWindowPanel\" (localizedPanelLabel(\"Render View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Render View\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"shapePanel\" (localizedPanelLabel(\"Shape Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tshapePanel -edit -l (localizedPanelLabel(\"Shape Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"posePanel\" (localizedPanelLabel(\"Pose Editor\")) `;\n\tif (\"\" != $panelName) {\n"
		+ "\t\t$label = `panel -q -label $panelName`;\n\t\tposePanel -edit -l (localizedPanelLabel(\"Pose Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"dynRelEdPanel\" (localizedPanelLabel(\"Dynamic Relationships\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Dynamic Relationships\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"relationshipPanel\" (localizedPanelLabel(\"Relationship Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Relationship Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"referenceEditorPanel\" (localizedPanelLabel(\"Reference Editor\")) `;\n"
		+ "\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Reference Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"dynPaintScriptedPanelType\" (localizedPanelLabel(\"Paint Effects\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Paint Effects\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"scriptEditorPanel\" (localizedPanelLabel(\"Script Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Script Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"profilerPanel\" (localizedPanelLabel(\"Profiler Tool\")) `;\n"
		+ "\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Profiler Tool\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"motionMakerEditorPanel\" (localizedPanelLabel(\"MotionMaker エディタ\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"MotionMaker エディタ\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"contentBrowserPanel\" (localizedPanelLabel(\"Content Browser\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Content Browser\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\tif ($useSceneConfig) {\n        string $configName = `getPanel -cwl (localizedPanelLabel(\"Current Layout\"))`;\n"
		+ "        if (\"\" != $configName) {\n\t\t\tpanelConfiguration -edit -label (localizedPanelLabel(\"Current Layout\")) \n\t\t\t\t-userCreated false\n\t\t\t\t-defaultImage \"vacantCell.png\"\n\t\t\t\t-image \"\"\n\t\t\t\t-sc false\n\t\t\t\t-configString \"global string $gMainPane; paneLayout -e -cn \\\"single\\\" -ps 1 100 100 $gMainPane;\"\n\t\t\t\t-removeAllPanels\n\t\t\t\t-ap false\n\t\t\t\t\t(localizedPanelLabel(\"Persp View\")) \n\t\t\t\t\t\"modelPanel\"\n"
		+ "\t\t\t\t\t\"$panelName = `modelPanel -unParent -l (localizedPanelLabel(\\\"Persp View\\\")) -mbv $menusOkayInPanels `;\\n$editorName = $panelName;\\nmodelEditor -e \\n    -cam `findStartUpCamera persp` \\n    -useInteractiveMode 0\\n    -displayLights \\\"default\\\" \\n    -displayAppearance \\\"smoothShaded\\\" \\n    -activeOnly 0\\n    -ignorePanZoom 0\\n    -wireframeOnShaded 0\\n    -headsUpDisplay 1\\n    -holdOuts 1\\n    -selectionHiliteDisplay 1\\n    -useDefaultMaterial 0\\n    -bufferMode \\\"double\\\" \\n    -twoSidedLighting 0\\n    -backfaceCulling 0\\n    -xray 0\\n    -jointXray 0\\n    -activeComponentsXray 0\\n    -displayTextures 0\\n    -smoothWireframe 0\\n    -lineWidth 1\\n    -textureAnisotropic 0\\n    -textureHilight 1\\n    -textureSampling 2\\n    -textureDisplay \\\"modulate\\\" \\n    -textureMaxSize 32768\\n    -fogging 0\\n    -fogSource \\\"fragment\\\" \\n    -fogMode \\\"linear\\\" \\n    -fogStart 0\\n    -fogEnd 100\\n    -fogDensity 0.1\\n    -fogColor 0.5 0.5 0.5 1 \\n    -depthOfFieldPreview 1\\n    -maxConstantTransparency 1\\n    -rendererName \\\"vp2Renderer\\\" \\n    -objectFilterShowInHUD 1\\n    -isFiltered 0\\n    -colorResolution 256 256 \\n    -bumpResolution 512 512 \\n    -textureCompression 0\\n    -transparencyAlgorithm \\\"frontAndBackCull\\\" \\n    -transpInShadows 0\\n    -cullingOverride \\\"none\\\" \\n    -lowQualityLighting 0\\n    -maximumNumHardwareLights 1\\n    -occlusionCulling 0\\n    -shadingModel 0\\n    -useBaseRenderer 0\\n    -useReducedRenderer 0\\n    -smallObjectCulling 0\\n    -smallObjectThreshold -1 \\n    -interactiveDisableShadows 0\\n    -interactiveBackFaceCull 0\\n    -sortTransparent 1\\n    -controllers 1\\n    -nurbsCurves 1\\n    -nurbsSurfaces 1\\n    -polymeshes 1\\n    -subdivSurfaces 1\\n    -planes 1\\n    -lights 1\\n    -cameras 1\\n    -controlVertices 1\\n    -hulls 1\\n    -grid 0\\n    -imagePlane 1\\n    -joints 1\\n    -ikHandles 1\\n    -deformers 1\\n    -dynamics 1\\n    -particleInstancers 1\\n    -fluids 1\\n    -hairSystems 1\\n    -follicles 1\\n    -nCloths 1\\n    -nParticles 1\\n    -nRigids 1\\n    -dynamicConstraints 1\\n    -locators 1\\n    -manipulators 1\\n    -pluginShapes 1\\n    -dimensions 1\\n    -handles 1\\n    -pivots 1\\n    -textures 1\\n    -strokes 1\\n    -motionTrails 1\\n    -clipGhosts 1\\n    -bluePencil 1\\n    -greasePencils 0\\n    -excludeObjectPreset \\\"すべて\\\" \\n    -shadows 0\\n    -captureSequenceNumber -1\\n    -width 1600\\n    -height 1000\\n    -sceneRenderFilter 0\\n    $editorName;\\nmodelEditor -e -viewSelected 0 $editorName;\\nmodelEditor -e \\n    -pluginObjects \\\"mayaUsdProxyShapeBaseDisplayFilter\\\" 1 \\n    $editorName\"\n"
		+ "\t\t\t\t\t\"modelPanel -edit -l (localizedPanelLabel(\\\"Persp View\\\")) -mbv $menusOkayInPanels  $panelName;\\n$editorName = $panelName;\\nmodelEditor -e \\n    -cam `findStartUpCamera persp` \\n    -useInteractiveMode 0\\n    -displayLights \\\"default\\\" \\n    -displayAppearance \\\"smoothShaded\\\" \\n    -activeOnly 0\\n    -ignorePanZoom 0\\n    -wireframeOnShaded 0\\n    -headsUpDisplay 1\\n    -holdOuts 1\\n    -selectionHiliteDisplay 1\\n    -useDefaultMaterial 0\\n    -bufferMode \\\"double\\\" \\n    -twoSidedLighting 0\\n    -backfaceCulling 0\\n    -xray 0\\n    -jointXray 0\\n    -activeComponentsXray 0\\n    -displayTextures 0\\n    -smoothWireframe 0\\n    -lineWidth 1\\n    -textureAnisotropic 0\\n    -textureHilight 1\\n    -textureSampling 2\\n    -textureDisplay \\\"modulate\\\" \\n    -textureMaxSize 32768\\n    -fogging 0\\n    -fogSource \\\"fragment\\\" \\n    -fogMode \\\"linear\\\" \\n    -fogStart 0\\n    -fogEnd 100\\n    -fogDensity 0.1\\n    -fogColor 0.5 0.5 0.5 1 \\n    -depthOfFieldPreview 1\\n    -maxConstantTransparency 1\\n    -rendererName \\\"vp2Renderer\\\" \\n    -objectFilterShowInHUD 1\\n    -isFiltered 0\\n    -colorResolution 256 256 \\n    -bumpResolution 512 512 \\n    -textureCompression 0\\n    -transparencyAlgorithm \\\"frontAndBackCull\\\" \\n    -transpInShadows 0\\n    -cullingOverride \\\"none\\\" \\n    -lowQualityLighting 0\\n    -maximumNumHardwareLights 1\\n    -occlusionCulling 0\\n    -shadingModel 0\\n    -useBaseRenderer 0\\n    -useReducedRenderer 0\\n    -smallObjectCulling 0\\n    -smallObjectThreshold -1 \\n    -interactiveDisableShadows 0\\n    -interactiveBackFaceCull 0\\n    -sortTransparent 1\\n    -controllers 1\\n    -nurbsCurves 1\\n    -nurbsSurfaces 1\\n    -polymeshes 1\\n    -subdivSurfaces 1\\n    -planes 1\\n    -lights 1\\n    -cameras 1\\n    -controlVertices 1\\n    -hulls 1\\n    -grid 0\\n    -imagePlane 1\\n    -joints 1\\n    -ikHandles 1\\n    -deformers 1\\n    -dynamics 1\\n    -particleInstancers 1\\n    -fluids 1\\n    -hairSystems 1\\n    -follicles 1\\n    -nCloths 1\\n    -nParticles 1\\n    -nRigids 1\\n    -dynamicConstraints 1\\n    -locators 1\\n    -manipulators 1\\n    -pluginShapes 1\\n    -dimensions 1\\n    -handles 1\\n    -pivots 1\\n    -textures 1\\n    -strokes 1\\n    -motionTrails 1\\n    -clipGhosts 1\\n    -bluePencil 1\\n    -greasePencils 0\\n    -excludeObjectPreset \\\"すべて\\\" \\n    -shadows 0\\n    -captureSequenceNumber -1\\n    -width 1600\\n    -height 1000\\n    -sceneRenderFilter 0\\n    $editorName;\\nmodelEditor -e -viewSelected 0 $editorName;\\nmodelEditor -e \\n    -pluginObjects \\\"mayaUsdProxyShapeBaseDisplayFilter\\\" 1 \\n    $editorName\"\n"
		+ "\t\t\t\t$configName;\n\n            setNamedPanelLayout (localizedPanelLabel(\"Current Layout\"));\n        }\n\n        panelHistory -e -clear mainPanelHistory;\n        sceneUIReplacement -clear;\n\t}\n\n\ngrid -spacing 5 -size 12 -divisions 5 -displayAxes yes -displayGridLines yes -displayDivisionLines yes -displayPerspectiveLabels no -displayOrthographicLabels no -displayAxesBold yes -perspectiveLabelPosition axis -orthographicLabelPosition edge;\nviewManip -drawCompass 0 -compassAngle 0 -frontParameters \"\" -homeParameters \"\" -selectionLockParameters \"\";\n}\n");
	setAttr ".st" 3;
createNode script -n "sceneConfigurationScriptNode";
	rename -uid "2F2E2A84-4C09-10D0-01BC-D9A0D5A4A9C6";
	setAttr ".b" -type "string" "playbackOptions -min 1 -max 120 -ast 1 -aet 200 ";
	setAttr ".st" 6;
select -ne :time1;
	setAttr ".o" 1;
	setAttr ".unw" 1;
select -ne :hardwareRenderingGlobals;
	setAttr ".otfna" -type "stringArray" 22 "NURBS Curves" "NURBS Surfaces" "Polygons" "Subdiv Surface" "Particles" "Particle Instance" "Fluids" "Strokes" "Image Planes" "UI" "Lights" "Cameras" "Locators" "Joints" "IK Handles" "Deformers" "Motion Trails" "Components" "Hair Systems" "Follicles" "Misc. UI" "Ornaments"  ;
	setAttr ".otfva" -type "Int32Array" 22 0 1 1 1 1 1
		 1 1 1 0 0 0 0 0 0 0 0 0
		 0 0 0 0 ;
	setAttr ".fprt" yes;
	setAttr ".rtfm" 1;
select -ne :renderPartition;
	setAttr -s 3 ".st";
select -ne :renderGlobalsList1;
select -ne :defaultShaderList1;
	setAttr -s 7 ".s";
select -ne :postProcessList1;
	setAttr -s 2 ".p";
select -ne :defaultRenderingList1;
select -ne :standardSurface1;
	setAttr ".bc" -type "float3" 0.40000001 0.40000001 0.40000001 ;
	setAttr ".sr" 0.5;
select -ne :openPBR_shader1;
	setAttr ".bc" -type "float3" 0.40000001 0.40000001 0.40000001 ;
	setAttr ".sr" 0.5;
select -ne :initialShadingGroup;
	setAttr ".ro" yes;
select -ne :initialParticleSE;
	setAttr ".ro" yes;
select -ne :defaultRenderGlobals;
	addAttr -ci true -h true -sn "dss" -ln "defaultSurfaceShader" -dt "string";
	setAttr ".dss" -type "string" "openPBR_shader1";
select -ne :defaultResolution;
	setAttr ".pa" 1;
select -ne :defaultColorMgtGlobals;
	setAttr ".cfe" yes;
	setAttr ".cfp" -type "string" "<MAYA_RESOURCES>/OCIO-configs/Maya2022-default/config.ocio";
	setAttr ".vtn" -type "string" "ACES 1.0 SDR-video (sRGB)";
	setAttr ".vn" -type "string" "ACES 1.0 SDR-video";
	setAttr ".dn" -type "string" "sRGB";
	setAttr ".wsn" -type "string" "ACEScg";
	setAttr ".otn" -type "string" "ACES 1.0 SDR-video (sRGB)";
	setAttr ".potn" -type "string" "ACES 1.0 SDR-video (sRGB)";
select -ne :hardwareRenderGlobals;
	setAttr ".ctrs" 256;
	setAttr ".btrs" 512;
connectAttr "aruRetopoNative1.om" "aruRetopoMesh1Shape.i";
connectAttr "aruRetopoNative1.om" "aruRetopoOverlayShape1.rtm";
relationship "link" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "aruRetopoPreviewSG1.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "aruRetopoPreviewSG1.message" ":defaultLightSet.message";
connectAttr "layerManager.dli[0]" "defaultLayer.id";
connectAttr "renderLayerManager.rlmi[0]" "defaultRenderLayer.rlid";
connectAttr "aruRetopoGuideShape1.ond" "aruRetopoGenerator1.gd";
connectAttr "aruRetopoGuideShape1.nd" "aruRetopoGenerator1.grd";
connectAttr "aruRetopoGuideShape1.opos" "aruRetopoGenerator1.gps";
connectAttr "aruRetopoGuideShape1.wm" "aruRetopoGenerator1.gm";
connectAttr "occlusionCylinderShape.w" "aruRetopoGenerator1.rm";
connectAttr "aruRetopoPreviewSG1.msg" "aruRetopoGenerator1.previewShadingGroup";
connectAttr "aruRetopoNative1.msg" "aruRetopoGenerator1.nativeBackend";
connectAttr "aruRetopoPlan1.msg" "aruRetopoGenerator1.nativePlan";
connectAttr "aruRetopoPreviewMaterial1.oc" "aruRetopoPreviewSG1.ss";
connectAttr "aruRetopoMesh1Shape.iog" "aruRetopoPreviewSG1.dsm" -na;
connectAttr "aruRetopoPreviewSG1.msg" "materialInfo1.sg";
connectAttr "aruRetopoPreviewMaterial1.msg" "materialInfo1.m";
connectAttr "aruRetopoGuideShape1.nd" "aruRetopoPlan1.guideData";
connectAttr "aruRetopoGuideShape1.opos" "aruRetopoPlan1.guidePositions";
connectAttr "occlusionCylinderShape.w" "aruRetopoPlan1.referenceMesh";
connectAttr "aruRetopoGuideShape1.wm" "aruRetopoPlan1.gm";
connectAttr "aruRetopoGenerator1.sps" "aruRetopoPlan1.selectedPatches";
connectAttr "aruRetopoGenerator1.sd" "aruRetopoPlan1.subdivisions";
connectAttr "aruRetopoGenerator1.rb" "aruRetopoPlan1.rebuildSerial";
connectAttr "aruRetopoGenerator1.gw" "aruRetopoPlan1.guideWeight";
connectAttr "aruRetopoGenerator1.msg" "aruRetopoNative1.retopoOwner";
connectAttr "aruRetopoPlan1.stencilOffsets" "aruRetopoNative1.so";
connectAttr "aruRetopoPlan1.stencilIndices" "aruRetopoNative1.si";
connectAttr "aruRetopoPlan1.stencilWeights" "aruRetopoNative1.sw";
connectAttr "aruRetopoPlan1.faceCounts" "aruRetopoNative1.fc";
connectAttr "aruRetopoPlan1.faceIndices" "aruRetopoNative1.fi";
connectAttr "aruRetopoPlan1.adjacencyOffsets" "aruRetopoNative1.ao";
connectAttr "aruRetopoPlan1.adjacencyIndices" "aruRetopoNative1.ai";
connectAttr "aruRetopoPlan1.guideWeights" "aruRetopoNative1.gw";
connectAttr "aruRetopoGuideShape1.opos" "aruRetopoNative1.pos";
connectAttr "occlusionCylinderShape.w" "aruRetopoNative1.rm";
connectAttr "aruRetopoGuideShape1.wm" "aruRetopoNative1.gm";
connectAttr "aruRetopoGenerator1.ri" "aruRetopoNative1.ri";
connectAttr "aruRetopoGenerator1.rs" "aruRetopoNative1.rs";
connectAttr "aruRetopoGenerator1.pg" "aruRetopoNative1.pg";
connectAttr "aruRetopoPreviewSG1.pa" ":renderPartition.st" -na;
connectAttr "aruRetopoPreviewMaterial1.msg" ":defaultShaderList1.s" -na;
connectAttr "defaultRenderLayer.msg" ":defaultRenderingList1.r" -na;
connectAttr "occlusionCylinderShape.iog" ":initialShadingGroup.dsm" -na;
// End of occlusion_cylinder_test.ma
