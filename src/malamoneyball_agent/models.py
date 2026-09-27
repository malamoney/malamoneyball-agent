from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NFLPlayerProjection(BaseModel):
    """One player's weekly projection from the Razzball API.

    Only the fields the projections tool returns are required. Everything else
    is optional, so a row missing or nulling an unused field still validates,
    and fields Razzball adds later are ignored.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    rotowireid: str | None = None
    nflid: str | None = None
    razz_playerid: str | None = None
    fname: str | None = None
    lname: str | None = None
    name: str
    pos: str
    team: str
    opp: str
    stadium: str | None = None
    season: int | None = None
    week: int | None = None

    std_pts: float
    halfppr_pts: float
    ppr_pts: float
    snaps: float | None = None

    cmp: float | None = None
    att: float | None = None
    comp_pct: float | None = None
    pass_yds: float | None = None
    qb_ypc: float | None = None
    qb_ypa: float | None = None
    pass_td: float | None = None
    interceptions: float | None = Field(default=None, alias="int")
    sacks: float | None = None

    rush: float | None = None
    rush_yds: float | None = None
    rush_avg: float | None = None
    run_td: float | None = None

    targets: float | None = None
    rec: float | None = None
    rec_yds: float | None = None
    rec_ypc: float | None = None
    rec_ypt: float | None = None
    rec_td: float | None = None

    fum: float | None = None
    fum_lost: float | None = None
    pass_tpc: float | None = None
    rush_tpc: float | None = None
    rec_tpc: float | None = None

    tackles: float | None = None
    tackles_solo: float | None = None
    tackles_ast: float | None = None
    sacks_def: float | None = None
    int_def: float | None = None
    fum_def: float | None = None
    fum_def_recovered: float | None = None
    pass_def: float | None = None
    saf: float | None = None
    td_def_return: float | None = None
    def_returnyards: float | None = None
    tfl: float | None = None
    rushes_def: float | None = None
    rush_yds_def: float | None = None
    receptions_def: float | None = None
    rec_yds_def: float | None = None
    tds_def: float | None = None
    points_allowed: float | None = None
    yards_allowed: float | None = None

    fg: float | None = None
    fga: float | None = None
    xp: float | None = None
    xpa: float | None = None
    fg_made_10_19: float | None = Field(default=None, alias="10-19_fg_made")
    fg_att_10_19: float | None = Field(default=None, alias="10-19_fg_att")
    fg_made_20_29: float | None = Field(default=None, alias="20-29_fg_made")
    fg_att_20_29: float | None = Field(default=None, alias="20-29_fg_att")
    fg_made_30_39: float | None = Field(default=None, alias="30-39_fg_made")
    fg_att_30_39: float | None = Field(default=None, alias="30-39_fg_att")
    fg_made_40_49: float | None = Field(default=None, alias="40-49_fg_made")
    fg_att_40_49: float | None = Field(default=None, alias="40-49_fg_att")
    fg_made_50_plus: float | None = Field(default=None, alias="50+_fg_made")
    fg_att_50_plus: float | None = Field(default=None, alias="50+_fg_att")

    updated: datetime | None = None

    id_draftkings: str | None = None
    id_fanduel: str | None = None
    id_yahoo: str | None = None
    name_draftkings: str | None = None
    name_fanduel: str | None = None
    name_yahoo: str | None = None

    snaps_share: float | None = None
    rush_share: float | None = None
    targets_share: float | None = None
    dk_pts: float
    fd_pts: float
    y_pts: float | None = None

    id_fantrax: str | None = None

    yards_passing_300: float | None = None
    yards_passing_400: float | None = None
    yards_rushing_100: float | None = None
    yards_rushing_150: float | None = None
    yards_receiving_100: float | None = None
    yards_receiving_150: float | None = None

    points_zero: float | None = Field(default=None, alias="Points_Zero")
    points_1to6: float | None = Field(default=None, alias="Points_1to6")
    points_7to13: float | None = Field(default=None, alias="Points_7to13")
    points_14to20: float | None = Field(default=None, alias="Points_14to20")
    points_21to27: float | None = Field(default=None, alias="Points_21to27")
    points_28to34: float | None = Field(default=None, alias="Points_28to34")
    points_35: float | None = Field(default=None, alias="Points_35")

    health: str | None = None
    id_nffc: str | None = None
    id_cbs_player: str | None = None
    id_sleeper: str | None = None
    curweek: int | None = None

    @field_validator("nflid", mode="before")
    @classmethod
    def normalize_nflid(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in {"none", ""}:
            return None
        return value

    @field_validator("id_fantrax")
    @classmethod
    def strip_fantrax_whitespace(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None
