# FBS home stadiums, lower 48. Hawaii is left out — the map is a CONUS
# Albers and a Honolulu inset is not worth it for one team.
# team | stadium | city | state | lat | lon
S = """
Michigan|Michigan Stadium|Ann Arbor|MI|42.2658|-83.7486
Ohio State|Ohio Stadium|Columbus|OH|40.0017|-83.0197
Penn State|Beaver Stadium|University Park|PA|40.8122|-77.8560
Michigan State|Spartan Stadium|East Lansing|MI|42.7280|-84.4847
Wisconsin|Camp Randall Stadium|Madison|WI|43.0700|-89.4126
Iowa|Kinnick Stadium|Iowa City|IA|41.6588|-91.5514
Minnesota|Huntington Bank Stadium|Minneapolis|MN|44.9764|-93.2247
Illinois|Memorial Stadium|Champaign|IL|40.0995|-88.2359
Indiana|Memorial Stadium|Bloomington|IN|39.1806|-86.5258
Purdue|Ross-Ade Stadium|West Lafayette|IN|40.4348|-86.9187
Northwestern|Ryan Field|Evanston|IL|42.0658|-87.6926
Nebraska|Memorial Stadium|Lincoln|NE|40.8206|-96.7057
Maryland|SECU Stadium|College Park|MD|38.9906|-76.9472
Rutgers|SHI Stadium|Piscataway|NJ|40.5137|-74.4650
UCLA|Rose Bowl|Pasadena|CA|34.1613|-118.1676
USC|Los Angeles Memorial Coliseum|Los Angeles|CA|34.0141|-118.2879
Oregon|Autzen Stadium|Eugene|OR|44.0584|-123.0685
Washington|Husky Stadium|Seattle|WA|47.6503|-122.3016
Alabama|Bryant-Denny Stadium|Tuscaloosa|AL|33.2083|-87.5504
Georgia|Sanford Stadium|Athens|GA|33.9497|-83.3733
LSU|Tiger Stadium|Baton Rouge|LA|30.4118|-91.1836
Tennessee|Neyland Stadium|Knoxville|TN|35.9550|-83.9250
Florida|Ben Hill Griffin Stadium|Gainesville|FL|29.6500|-82.3486
Auburn|Jordan-Hare Stadium|Auburn|AL|32.6025|-85.4894
Texas A&M|Kyle Field|College Station|TX|30.6100|-96.3403
Texas|Darrell K Royal-Texas Memorial Stadium|Austin|TX|30.2837|-97.7325
Oklahoma|Gaylord Family Oklahoma Memorial Stadium|Norman|OK|35.2058|-97.4423
Missouri|Faurot Field|Columbia|MO|38.9358|-92.3333
Arkansas|Donald W. Reynolds Razorback Stadium|Fayetteville|AR|36.0680|-94.1786
Ole Miss|Vaught-Hemingway Stadium|Oxford|MS|34.3619|-89.5347
Mississippi State|Davis Wade Stadium|Starkville|MS|33.4560|-88.7940
Kentucky|Kroger Field|Lexington|KY|38.0221|-84.5053
South Carolina|Williams-Brice Stadium|Columbia|SC|33.9731|-81.0193
Vanderbilt|FirstBank Stadium|Nashville|TN|36.1447|-86.8083
Kansas|David Booth Kansas Memorial Stadium|Lawrence|KS|38.9631|-95.2469
Kansas State|Bill Snyder Family Stadium|Manhattan|KS|39.2019|-96.5936
Iowa State|Jack Trice Stadium|Ames|IA|42.0140|-93.6358
Oklahoma State|Boone Pickens Stadium|Stillwater|OK|36.1269|-97.0656
Texas Tech|Jones AT&T Stadium|Lubbock|TX|33.5906|-101.8725
TCU|Amon G. Carter Stadium|Fort Worth|TX|32.7098|-97.3684
Baylor|McLane Stadium|Waco|TX|31.5589|-97.1156
Houston|TDECU Stadium|Houston|TX|29.7217|-95.3494
Cincinnati|Nippert Stadium|Cincinnati|OH|39.1314|-84.5169
UCF|FBC Mortgage Stadium|Orlando|FL|28.6078|-81.1925
BYU|LaVell Edwards Stadium|Provo|UT|40.2578|-111.6547
West Virginia|Milan Puskar Stadium|Morgantown|WV|39.6497|-79.9550
Utah|Rice-Eccles Stadium|Salt Lake City|UT|40.7600|-111.8486
Arizona|Arizona Stadium|Tucson|AZ|32.2286|-110.9489
Arizona State|Mountain America Stadium|Tempe|AZ|33.4264|-111.9325
Colorado|Folsom Field|Boulder|CO|40.0097|-105.2669
Clemson|Memorial Stadium|Clemson|SC|34.6787|-82.8434
Florida State|Doak Campbell Stadium|Tallahassee|FL|30.4381|-84.3044
Miami|Hard Rock Stadium|Miami Gardens|FL|25.9580|-80.2389
North Carolina|Kenan Memorial Stadium|Chapel Hill|NC|35.9069|-79.0478
NC State|Carter-Finley Stadium|Raleigh|NC|35.8003|-78.7197
Duke|Wallace Wade Stadium|Durham|NC|36.0009|-78.9425
Wake Forest|Allegacy Stadium|Winston-Salem|NC|36.1319|-80.2564
Virginia|Scott Stadium|Charlottesville|VA|38.0311|-78.5133
Virginia Tech|Lane Stadium|Blacksburg|VA|37.2200|-80.4183
Pittsburgh|Acrisure Stadium|Pittsburgh|PA|40.4468|-80.0158
Syracuse|JMA Wireless Dome|Syracuse|NY|43.0362|-76.1361
Boston College|Alumni Stadium|Chestnut Hill|MA|42.3350|-71.1664
Louisville|L&N Federal Credit Union Stadium|Louisville|KY|38.2064|-85.7550
Georgia Tech|Bobby Dodd Stadium|Atlanta|GA|33.7725|-84.3928
SMU|Gerald J. Ford Stadium|Dallas|TX|32.8394|-96.7833
California|California Memorial Stadium|Berkeley|CA|37.8715|-122.2508
Stanford|Stanford Stadium|Stanford|CA|37.4347|-122.1614
Oregon State|Reser Stadium|Corvallis|OR|44.5594|-123.2817
Washington State|Martin Stadium|Pullman|WA|46.7311|-117.1633
Army|Michie Stadium|West Point|NY|41.3878|-73.9639
Navy|Navy-Marine Corps Memorial Stadium|Annapolis|MD|38.9853|-76.5083
Memphis|Simmons Bank Liberty Stadium|Memphis|TN|35.1211|-89.9422
Tulane|Yulman Stadium|New Orleans|LA|29.9411|-90.1189
South Florida|Raymond James Stadium|Tampa|FL|27.9759|-82.5033
East Carolina|Dowdy-Ficklen Stadium|Greenville|NC|35.5978|-77.3689
Temple|Lincoln Financial Field|Philadelphia|PA|39.9008|-75.1675
Charlotte|Jerry Richardson Stadium|Charlotte|NC|35.3097|-80.7378
Florida Atlantic|FAU Stadium|Boca Raton|FL|26.3722|-80.1017
North Texas|DATCU Stadium|Denton|TX|33.2072|-97.1531
Rice|Rice Stadium|Houston|TX|29.7161|-95.4092
Tulsa|Skelly Field at H.A. Chapman Stadium|Tulsa|OK|36.1489|-95.9450
UAB|Protective Stadium|Birmingham|AL|33.5197|-86.8033
UTSA|Alamodome|San Antonio|TX|29.4169|-98.4786
Boise State|Albertsons Stadium|Boise|ID|43.6028|-116.1961
Air Force|Falcon Stadium|Colorado Springs|CO|38.9972|-104.8433
Colorado State|Canvas Stadium|Fort Collins|CO|40.5714|-105.0844
Fresno State|Valley Children's Stadium|Fresno|CA|36.8139|-119.7375
Nevada|Mackay Stadium|Reno|NV|39.5456|-119.8161
New Mexico|University Stadium|Albuquerque|NM|35.0664|-106.6289
San Diego State|Snapdragon Stadium|San Diego|CA|32.7831|-117.1194
San Jose State|CEFCU Stadium|San Jose|CA|37.3194|-121.8686
UNLV|Allegiant Stadium|Las Vegas|NV|36.0909|-115.1833
Utah State|Maverik Stadium|Logan|UT|41.7514|-111.8114
Wyoming|War Memorial Stadium|Laramie|WY|41.3117|-105.5669
Appalachian State|Kidd Brewer Stadium|Boone|NC|36.2114|-81.6858
Coastal Carolina|Brooks Stadium|Conway|SC|33.7936|-79.0117
Georgia Southern|Paulson Stadium|Statesboro|GA|32.4194|-81.7825
Georgia State|Center Parc Stadium|Atlanta|GA|33.7361|-84.3892
James Madison|Bridgeforth Stadium|Harrisonburg|VA|38.4342|-78.8697
Marshall|Joan C. Edwards Stadium|Huntington|WV|38.4181|-82.4256
Old Dominion|S.B. Ballard Stadium|Norfolk|VA|36.8858|-76.3053
Arkansas State|Centennial Bank Stadium|Jonesboro|AR|35.8489|-90.6708
Louisiana|Cajun Field|Lafayette|LA|30.2136|-92.0483
Louisiana-Monroe|Malone Stadium|Monroe|LA|32.5286|-92.0708
South Alabama|Hancock Whitney Stadium|Mobile|AL|30.6969|-88.1836
Southern Miss|M.M. Roberts Stadium|Hattiesburg|MS|31.3292|-89.3336
Texas State|UFCU Stadium|San Marcos|TX|29.8894|-97.9264
Troy|Veterans Memorial Stadium|Troy|AL|31.8036|-85.9522
Akron|InfoCision Stadium|Akron|OH|41.0725|-81.5083
Ball State|Scheumann Stadium|Muncie|IN|40.2100|-85.4083
Bowling Green|Doyt Perry Stadium|Bowling Green|OH|41.3814|-83.6208
Buffalo|UB Stadium|Amherst|NY|43.0006|-78.7811
Central Michigan|Kelly/Shorts Stadium|Mount Pleasant|MI|43.5892|-84.7783
Eastern Michigan|Rynearson Stadium|Ypsilanti|MI|42.2372|-83.6339
Kent State|Dix Stadium|Kent|OH|41.1436|-81.3306
Miami (OH)|Yager Stadium|Oxford|OH|39.5117|-84.7292
Northern Illinois|Huskie Stadium|DeKalb|IL|41.9328|-88.7783
Ohio|Peden Stadium|Athens|OH|39.3222|-82.1075
Toledo|Glass Bowl|Toledo|OH|41.6586|-83.6136
Western Michigan|Waldo Stadium|Kalamazoo|MI|42.2833|-85.6114
UMass|McGuirk Alumni Stadium|Amherst|MA|42.3728|-72.5300
Liberty|Williams Stadium|Lynchburg|VA|37.3556|-79.1750
Jacksonville State|Burgess-Snow Field|Jacksonville|AL|33.8225|-85.7647
Sam Houston|Elliott T. Bowers Stadium|Huntsville|TX|30.7078|-95.5397
Western Kentucky|Houchens Industries-L.T. Smith Stadium|Bowling Green|KY|36.9803|-86.4611
Middle Tennessee|Floyd Stadium|Murfreesboro|TN|35.8483|-86.3661
Louisiana Tech|Joe Aillet Stadium|Ruston|LA|32.5306|-92.6503
New Mexico State|Aggie Memorial Stadium|Las Cruces|NM|32.2803|-106.7431
UTEP|Sun Bowl|El Paso|TX|31.7717|-106.5033
Florida International|Pitbull Stadium|Miami|FL|25.7508|-80.3792
Kennesaw State|Fifth Third Bank Stadium|Kennesaw|GA|34.0294|-84.5678
Delaware|Delaware Stadium|Newark|DE|39.6797|-75.7550
Missouri State|Robert W. Plaster Stadium|Springfield|MO|37.2000|-93.2828
Notre Dame|Notre Dame Stadium|South Bend|IN|41.6983|-86.2339
UConn|Pratt & Whitney Stadium|East Hartford|CT|41.7592|-72.6461
"""

STATE_NAMES = {
    "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida",
    "GA": "Georgia", "IA": "Iowa", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "MA": "Massachusetts", "MD": "Maryland", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "NC": "North Carolina",
    "NE": "Nebraska", "NJ": "New Jersey", "NM": "New Mexico", "NV": "Nevada",
    "NY": "New York", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "SC": "South Carolina", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VA": "Virginia", "WA": "Washington",
    "WI": "Wisconsin", "WV": "West Virginia", "WY": "Wyoming",
}


def load():
    out = []
    for line in S.strip().splitlines():
        team, stadium, city, st, lat, lon = line.split("|")
        out.append({"team": team, "stadium": stadium, "city": city,
                    "state": st, "lat": float(lat), "lon": float(lon)})
    return out
