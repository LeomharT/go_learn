package controller

import "github.com/gin-gonic/gin"

type Response struct {
	Code int         `json:"code"`
	Msg  string      `json:"msg"`
	Data interface{} `json:"data"`
}

func APIResponse(ctx *gin.Context, status int, msg string, data interface{}) Response {
	return Response{
		Code: status,
		Msg:  msg,
		Data: data,
	}
}
