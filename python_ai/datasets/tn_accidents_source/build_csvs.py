import pandas as pd, re
raw = pd.read_csv('/mnt/user-data/uploads/tn_accidents_raw.csv', header=0, dtype=str, keep_default_na=False)
raw.columns = ['page'] + [f'c{i}' for i in range(1, 43)]
OUT = '/mnt/user-data/outputs/tn_accidents_2023/'

def rows(pg):
    out = []
    for _, r in raw[raw.page == str(pg)].iterrows():
        v = [x.replace('\n', ' ').strip() for k, x in r.items() if k != 'page' and x.strip()]
        out.append(v)
    return out

def num(x):
    return float(x.replace(',', '')) if re.fullmatch(r'-?[\d,]+(\.\d+)?', x.strip()) else None

def iN(x):
    n = num(x)
    return None if n is None else int(n)   # 'NA' = district did not exist in 2021 (Mayiladuthurai)

CANON = {'TIRUCHIRAPALLI':'TIRUCHIRAPPALLI','TIRUPPUR':'TIRUPPUR','TIRUPUR':'TIRUPPUR','TIRUPATHUR':'TIRUPATTUR',
         'MYILADUTHURAI':'MAYILADUTHURAI','PUDUKKOTTAI':'PUDUKOTTAI','KANNIYAKUMARI':'KANYAKUMARI','CHENNAI':'CHENNAI CITY','THIRUVANNAMALAI':'TIRUVANNAMALAI','MYYILADUTHURAI':'MAYILADUTHURAI'}
def canon(n):
    n = re.sub(r'\s+', ' ', n.upper().strip())
    return CANON.get(n, n)

months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

# ---- district tables
def monthly(pg, name):
    recs = []
    rs = rows(pg)
    for i, v in enumerate(rs):
        if len(v) == 13 and num(v[0]) is not None and i + 1 < len(rs) and len(rs[i+1]) == 1:
            v = [rs[i+1][0]] + v          # name was split onto the next row by the PDF extractor
        if len(v) == 14 and num(v[1]) is not None:
            d = canon(v[0])
            if d in ('TOTAL','GRAND TOTAL'): continue
            vals = [int(num(x)) for x in v[1:13]]
            assert sum(vals) == int(num(v[13])), (name, d)
            for m, x in zip(months, vals): recs.append((d, m, x))
    df = pd.DataFrame(recs, columns=['district', 'month', name])
    assert df.district.nunique() == 38, (name, df.district.nunique())
    return df

acc = monthly(8, 'accidents'); dea = monthly(9, 'deaths'); hel = monthly(22, 'helmet_non_wearing_deaths')
m = acc.merge(dea, on=['district','month'], how='outer').merge(hel, on=['district','month'], how='outer')
assert len(m) == 456 and m.isna().sum().sum() == 0 and m.district.nunique() == 38
m['month_num'] = m.month.map({k: i+1 for i, k in enumerate(months)})
m.insert(0, 'year', 2023)
m = m.sort_values(['district','month_num'])[['year','district','month_num','month','accidents','deaths','helmet_non_wearing_deaths']]
m.to_csv(OUT+'01_district_monthly_2023.csv', index=False)

# ---- district summary
s = {}
for v in rows(3):
    if len(v) == 4 and v[0].isdigit(): s[canon(v[1])] = dict(total_accidents=int(num(v[2])), total_deaths=int(num(v[3])))
for v in rows(6):
    if len(v) == 4 and v[0].isdigit(): s[canon(v[1])].update(grievous_injured=int(num(v[2])), minor_injured=int(num(v[3])))
for v in rows(13):
    if len(v) == 10 and num(v[1]) is not None and v[0] != 'TOTAL':
        s[canon(v[0])].update(hotspots_identified=int(num(v[1])), hotspots_funded=int(num(v[2])))
for v in rows(10):
    if len(v) == 12 and v[0].isdigit():
        s[canon(v[1])].update(accidents_2021=iN(v[2]), accidents_2022=iN(v[3]), deaths_2021=iN(v[7]), deaths_2022=iN(v[8]))
S = pd.DataFrame.from_dict(s, orient='index').rename_axis('district').reset_index()
assert len(S) == 38 and S.isna().sum().sum() == 2 and S.drop(columns=['accidents_2021','deaths_2021']).isna().sum().sum() == 0
S['fatality_per_100_accidents'] = (S.total_deaths / S.total_accidents * 100).round(2)
S['injured_total'] = S.grievous_injured + S.minor_injured
S.to_csv(OUT+'02_district_summary_2023.csv', index=False)
print('state totals', S.total_accidents.sum(), S.total_deaths.sum(), S.grievous_injured.sum(), S.minor_injured.sum(), S.accidents_2021.sum(), S.accidents_2022.sum())

# ---- state monthly
recs = []
for v in rows(16):
    if v and v[0] in ['January','February','March','April','May','June','July','August','September','October','November','December'] and len(v) == 16:
        recs.append(dict(month=v[0], accidents_2021=int(num(v[1])), accidents_2022=int(num(v[2])), accidents_2023=int(num(v[3])),
                         fatal_accidents_2021=int(num(v[6])), fatal_accidents_2022=int(num(v[7])), fatal_accidents_2023=int(num(v[8])),
                         deaths_2021=int(num(v[11])), deaths_2022=int(num(v[12])), deaths_2023=int(num(v[13]))))
M = pd.DataFrame(recs); assert len(M) == 12
two = [v for v in rows(21) if len(v) == 3 and num(v[1]) is not None and v[0] != 'Total']
assert len(two) == 12
M['two_wheeler_deaths_2023'] = [int(num(v[1])) for v in two]
M['helmet_non_wearing_deaths_2023'] = [int(num(v[2])) for v in two]
off = [v for v in rows(26) if len(v) == 8 and v[0].endswith('-23')]
assert len(off) == 12
for j, c in enumerate(['over_speeding','overload_goods','persons_in_goods_vehicle','mobile_phone_use','drunken_driving','red_light_jumping','total_offences'], 1):
    M['enforcement_'+c+'_2023'] = [int(num(v[j])) for v in off]
M.insert(0, 'month_num', range(1, 13))
M.to_csv(OUT+'03_state_monthly_2021_2023_and_enforcement.csv', index=False)
print('state monthly totals', M.accidents_2023.sum(), M.deaths_2023.sum(), M.two_wheeler_deaths_2023.sum(), M.enforcement_drunken_driving_2023.sum())

# ---- vehicle, road type
def two_year(pg, key, label):
    r = []
    for v in rows(pg):
        if len(v) == 7 and num(v[1]) is not None:
            r.append({label: v[0].lstrip(': ').strip() if v[0].startswith(':') else v[0], 'accidents_2022': int(num(v[1])), 'accidents_2023': int(num(v[2])),
                      'deaths_2022': int(num(v[4])), 'deaths_2023': int(num(v[5]))})
    return pd.DataFrame(r)
V = two_year(19, 'v', 'vehicle_type')
V.loc[V.vehicle_type == 'PRIVATE', 'vehicle_type'] = 'Bus: PRIVATE'; V.loc[V.vehicle_type == 'Bus : GOVT', 'vehicle_type'] = 'Bus: GOVT'
V['vehicle_type'] = V.vehicle_type.str.replace(r'\s+', ' ', regex=True).str.replace('Taxi /Van', 'Taxi / Van', regex=False)
V.to_csv(OUT+'04_by_vehicle_type.csv', index=False)
R = two_year(23, 'r', 'road_type'); R.to_csv(OUT+'05_by_road_type.csv', index=False)
assert V.accidents_2023.iloc[-1] == 67213 and R.accidents_2023.iloc[-1] == 67213
assert V.accidents_2023[:-1].sum() == 67213 and R.accidents_2023[:-1].sum() == 67213

# ---- causes (by fault)
C = []
for v in rows(25):
    if len(v) == 9 and num(v[1]) is not None:
        C.append(dict(cause_fault_of=v[0], fatal_accidents=int(num(v[1])), persons_killed=int(num(v[2])), grievous_accidents=int(num(v[3])),
                      grievous_persons=int(num(v[4])), minor_accidents=int(num(v[5])), minor_persons=int(num(v[6])),
                      non_injury_accidents=int(num(v[7])), total_accidents=int(num(v[8]))))
C = pd.DataFrame(C); C.to_csv(OUT+'06_by_cause_2023.csv', index=False)
print(C.tail(2).to_string())
print('cause col sums', C[:-1].total_accidents.sum(), C[:-1].persons_killed.sum())

# ---- major cities / commissionerates
K = []
for v in rows(14):
    if len(v) == 9 and num(v[1]) is not None:
        K.append(dict(city=v[0], fatal_accidents=int(num(v[1])), persons_killed=int(num(v[2])), grievous_accidents=int(num(v[3])), grievous_persons=int(num(v[4])),
                      minor_accidents=int(num(v[5])), minor_persons=int(num(v[6])), non_injury_accidents=int(num(v[7])), total_accidents=int(num(v[8]))))
K = pd.DataFrame(K); K.to_csv(OUT+'07_major_cities_2023.csv', index=False); print(len(K))

# ---- yearly trend
Y = []
for v in rows(15):
    if len(v) == 6 and v[0].isdigit() and len(v[0]) == 4:
        Y.append(dict(year=int(v[0]), vehicles_registered=int(num(v[1])), total_accidents=int(num(v[2])), fatal_accidents=int(num(v[3])), fatalities=int(num(v[4])), pct_change_fatalities=float(v[5])))
Y = pd.DataFrame(Y); print(len(Y)); Y.to_csv(OUT+'08_state_yearly_2012_2023.csv', index=False)
