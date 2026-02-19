from datetime import timedelta


class Settings:
    # High velocity configuration
    HIGH_VELOCITY_WINDOW: timedelta = timedelta(hours=24)
    HIGH_VELOCITY_THRESHOLD: int = 30  # total tx (in+out) within window

    # Smurfing configuration
    SMURF_WINDOW: timedelta = timedelta(hours=72)
    SMURF_MIN_COUNTERPARTIES: int = 10

    # Shell / layering configuration
    SHELL_MIN_HOPS: int = 3  # path length in edges
    SHELL_MAX_INTERMEDIATE_TX_COUNT: int = 3

    # Scoring weights
    SCORE_CYCLE: float = 40.0
    SCORE_FAN_IN: float = 30.0
    SCORE_FAN_OUT: float = 30.0
    SCORE_SHELL: float = 35.0
    SCORE_HIGH_VELOCITY: float = 10.0
    SCORE_MAX: float = 100.0

    # False positive control heuristics
    MERCHANT_TX_COUNT_THRESHOLD: int = 300
    MERCHANT_AMOUNT_CV_THRESHOLD: float = 0.3
    MERCHANT_MIN_OBSERVATION_DAYS: int = 14

    PAYROLL_TX_COUNT_THRESHOLD: int = 100
    PAYROLL_AMOUNT_CV_THRESHOLD: float = 0.2
    PAYROLL_MIN_PAY_DATES: int = 3


settings = Settings()



