package service

type Log struct {
	Time    string `json:"time"`
	Level   string `json:"level"`
	Message string `json:"message"`
}

func (c *Service) GetLogsList() Log {
	return Log{
		Time:    "2026-08-26 18:30:00",
		Level:   "INFO",
		Message: "service started",
	}
}
