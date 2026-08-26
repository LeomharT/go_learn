// @title           Swagger Example API
// @version         1.0
// @description     This is a sample server of logs server.
// @termsOfService  http://swagger.io/terms/

// @contact.name   API Support
// @contact.url    http://www.swagger.io/support
// @contact.email  support@swagger.io

// @license.name  Apache 2.0
// @license.url   http://www.apache.org/licenses/LICENSE-2.0.html

// @host      localhost:8080
// @BasePath  /api/v1

// @securityDefinitions.basic  BasicAuth

// @externalDocs.description  OpenAPI
// @externalDocs.url          https://swagger.io/resources/open-api/

package main

import (
	"log"
	"net/http"

	"go_learn/controller"
	_ "go_learn/docs"
	"go_learn/service"

	"github.com/gin-gonic/gin"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
)

func main() {
	// Create a Gin router with default middleware (logger and recovery)
	r := gin.Default()
	s := service.NewService()
	c := controller.NewController(s)

	v1 := r.Group("/api/v1")
	{
		logs := v1.Group("/logs")
		{
			logs.GET("", c.GetLogsList)
		}
	}

	// Define a simple GET endpoint
	r.GET("/", func(c *gin.Context) {
		// Return JSON response
		c.JSON(http.StatusOK, gin.H{
			"message": "Hello World!" + "leoliao hello",
		})
	})
	r.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerFiles.Handler))

	// Start server on port 8080 (default)
	// Server will listen on 0.0.0.0:8080 (localhost:8080 on Windows)
	if err := r.Run(); err != nil {
		log.Fatalf("failed to run server: %v", err)
	}
}
