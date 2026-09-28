from pathlib import Path
p=Path('tests/projection_certificates_cases.py');s=p.read_text().replace("base=load('numeric_t16');candidate=load('certificates')", "candidate_name=os.environ.get('ARU_TEST_CERTIFICATE_CANDIDATE','certificates')\nbase=load('numeric_t16');candidate=load(candidate_name)")
s=s.replace("'passed':True,", "'passed':True,'candidate':candidate_name,")
s=s.replace("'projection_certificates_cases_'+cmds.about(version=True)", "'projection_certificates_cases_'+candidate_name+'_'+cmds.about(version=True)")
p.write_text(s)
