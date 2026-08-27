package model

type Log struct {
	Time    string `json:"time"`
	Level   string `json:"level"`
	Content string `json:"content"`
}
