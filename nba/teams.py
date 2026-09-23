from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamInfo:
    name: str
    tricode: str
    team_id: int
    latitude: float
    longitude: float
    timezone: str
    altitude_m: float = 0.0


_TEAMS = (
    ("Atlanta Hawks","ATL",1610612737,33.7573,-84.3963,"America/New_York",320),
    ("Boston Celtics","BOS",1610612738,42.3662,-71.0621,"America/New_York",8),
    ("Brooklyn Nets","BKN",1610612751,40.6826,-73.9754,"America/New_York",10),
    ("Charlotte Hornets","CHA",1610612766,35.2251,-80.8392,"America/New_York",229),
    ("Chicago Bulls","CHI",1610612741,41.8807,-87.6742,"America/Chicago",181),
    ("Cleveland Cavaliers","CLE",1610612739,41.4965,-81.6882,"America/New_York",199),
    ("Dallas Mavericks","DAL",1610612742,32.7905,-96.8103,"America/Chicago",131),
    ("Denver Nuggets","DEN",1610612743,39.7487,-105.0077,"America/Denver",1609),
    ("Detroit Pistons","DET",1610612765,42.3410,-83.0550,"America/Detroit",183),
    ("Golden State Warriors","GSW",1610612744,37.7680,-122.3877,"America/Los_Angeles",5),
    ("Houston Rockets","HOU",1610612745,29.7508,-95.3621,"America/Chicago",15),
    ("Indiana Pacers","IND",1610612754,39.7640,-86.1555,"America/Indiana/Indianapolis",218),
    ("LA Clippers","LAC",1610612746,33.9535,-118.3390,"America/Los_Angeles",30),
    ("Los Angeles Lakers","LAL",1610612747,34.0430,-118.2673,"America/Los_Angeles",71),
    ("Memphis Grizzlies","MEM",1610612763,35.1382,-90.0506,"America/Chicago",79),
    ("Miami Heat","MIA",1610612748,25.7814,-80.1870,"America/New_York",2),
    ("Milwaukee Bucks","MIL",1610612749,43.0451,-87.9172,"America/Chicago",188),
    ("Minnesota Timberwolves","MIN",1610612750,44.9795,-93.2760,"America/Chicago",253),
    ("New Orleans Pelicans","NOP",1610612740,29.9490,-90.0821,"America/Chicago",1),
    ("New York Knicks","NYK",1610612752,40.7505,-73.9934,"America/New_York",10),
    ("Oklahoma City Thunder","OKC",1610612760,35.4634,-97.5151,"America/Chicago",366),
    ("Orlando Magic","ORL",1610612753,28.5392,-81.3839,"America/New_York",25),
    ("Philadelphia 76ers","PHI",1610612755,39.9012,-75.1720,"America/New_York",12),
    ("Phoenix Suns","PHX",1610612756,33.4457,-112.0712,"America/Phoenix",331),
    ("Portland Trail Blazers","POR",1610612757,45.5316,-122.6668,"America/Los_Angeles",9),
    ("Sacramento Kings","SAC",1610612758,38.5802,-121.4997,"America/Los_Angeles",9),
    ("San Antonio Spurs","SAS",1610612759,29.4270,-98.4375,"America/Chicago",198),
    ("Toronto Raptors","TOR",1610612761,43.6435,-79.3791,"America/Toronto",76),
    ("Utah Jazz","UTA",1610612762,40.7683,-111.9011,"America/Denver",1288),
    ("Washington Wizards","WAS",1610612764,38.8981,-77.0209,"America/New_York",7),
)

TEAMS = {row[0]: TeamInfo(*row) for row in _TEAMS}
BY_TRICODE = {t.tricode: t for t in TEAMS.values()}
BY_ID = {t.team_id: t for t in TEAMS.values()}

ALIASES = {
    "Los Angeles Clippers": "LA Clippers",
    "LA Clippers": "LA Clippers",
}


def canonical_team(name: str) -> str:
    clean = " ".join(str(name).split())
    return ALIASES.get(clean, clean)


def team_info(name_or_tricode: str) -> TeamInfo:
    value = canonical_team(name_or_tricode)
    if value in TEAMS:
        return TEAMS[value]
    code = value.upper()
    if code in BY_TRICODE:
        return BY_TRICODE[code]
    raise KeyError(f"unknown NBA team: {name_or_tricode}")
