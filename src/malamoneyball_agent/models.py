from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NFLPlayerProjection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rotowireid: str
    nflid: str | None
    razz_playerid: str
    fname: str
    lname: str
    name: str
    pos: str
    team: str
    opp: str
    stadium: str
    season: int
    week: int

    std_pts: float
    halfppr_pts: float
    ppr_pts: float
    snaps: float

    cmp: float
    att: float
    comp_pct: float
    pass_yds: float
    qb_ypc: float
    qb_ypa: float
    pass_td: float
    interceptions: float = Field(alias="int")
    sacks: float

    rush: float
    rush_yds: float
    rush_avg: float
    run_td: float

    targets: float
    rec: float
    rec_yds: float
    rec_ypc: float
    rec_ypt: float
    rec_td: float

    fum: float
    fum_lost: float
    pass_tpc: float
    rush_tpc: float
    rec_tpc: float

    tackles: float
    tackles_solo: float
    tackles_ast: float
    sacks_def: float
    int_def: float
    fum_def: float
    fum_def_recovered: float
    pass_def: float
    saf: float
    td_def_return: float
    def_returnyards: float
    tfl: float
    rushes_def: float
    rush_yds_def: float
    receptions_def: float
    rec_yds_def: float
    tds_def: float
    points_allowed: float
    yards_allowed: float

    fg: float
    fga: float
    xp: float
    xpa: float
    fg_made_10_19: float = Field(alias="10-19_fg_made")
    fg_att_10_19: float = Field(alias="10-19_fg_att")
    fg_made_20_29: float = Field(alias="20-29_fg_made")
    fg_att_20_29: float = Field(alias="20-29_fg_att")
    fg_made_30_39: float = Field(alias="30-39_fg_made")
    fg_att_30_39: float = Field(alias="30-39_fg_att")
    fg_made_40_49: float = Field(alias="40-49_fg_made")
    fg_att_40_49: float = Field(alias="40-49_fg_att")
    fg_made_50_plus: float = Field(alias="50+_fg_made")
    fg_att_50_plus: float = Field(alias="50+_fg_att")

    updated: datetime

    id_draftkings: str
    id_fanduel: str
    id_yahoo: str
    name_draftkings: str
    name_fanduel: str
    name_yahoo: str

    snaps_share: float
    rush_share: float
    targets_share: float
    dk_pts: float
    fd_pts: float
    y_pts: float

    id_fantrax: str

    yards_passing_300: float
    yards_passing_400: float
    yards_rushing_100: float
    yards_rushing_150: float
    yards_receiving_100: float
    yards_receiving_150: float

    points_zero: float = Field(alias="Points_Zero")
    points_1to6: float = Field(alias="Points_1to6")
    points_7to13: float = Field(alias="Points_7to13")
    points_14to20: float = Field(alias="Points_14to20")
    points_21to27: float = Field(alias="Points_21to27")
    points_28to34: float = Field(alias="Points_28to34")
    points_35: float = Field(alias="Points_35")

    health: str
    id_nffc: str
    id_cbs_player: str
    id_sleeper: str
    curweek: int

    @field_validator("nflid", mode="before")
    @classmethod
    def normalize_nflid(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in {"none", ""}:
            return None
        return value

    @field_validator("id_fantrax")
    @classmethod
    def strip_fantrax_whitespace(cls, value: str) -> str:
        return value.strip()
