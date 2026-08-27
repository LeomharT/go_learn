package service

import (
	"go_learn/model"
	"os"
	"path/filepath"
)

func (c *Service) GetLogsList() (model.Log, error) {
	path := filepath.Join("tmp", "gs", "edge-core", "logs", "edge-core-20260825.log")
	absPath, err := filepath.Abs((path))

	if err != nil {
		return model.Log{
			Time:    "2026-08-26 18:30:00",
			Level:   "Error",
			Content: "Logs not found",
		}, err
	}

	data, err := os.ReadFile(absPath)

	if err != nil {
		return model.Log{
			Time:    "2026-08-26 18:30:00",
			Level:   "ERROR",
			Content: err.Error(),
		}, err
	}

	return model.Log{
		Time:    "2026-08-26 18:30:00",
		Level:   "INFO",
		Content: string(data),
	}, nil
}
