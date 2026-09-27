package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sort"
)

func hello(w http.ResponseWriter, req *http.Request) {
	fmt.Fprint(w, "hello\n")
}

// This is what OTP's GraphQL returns when you call plan()
// const sampleResponse = `...` (removed — now calling OTP live)

type OTPResponse struct {
	Data struct {
		Plan struct {
			Itineraries []struct {
				Duration int   `json:"duration"`
				Legs     []Leg `json:"legs"`
			} `json:"itineraries"`
		} `json:"plan"`
	} `json:"data"`
}
type Leg struct {
	Mode     string  `json:"mode"`
	Duration float64 `json:"duration"`
	Distance float64 `json:"distance"`
	From     struct {
		Name string `json:"name"`
	} `json:"from"`
	To struct {
		Name string `json:"name"`
	} `json:"to"`
	Route struct {
		ShortName string `json:"shortName"`
		Agency    struct {
			Name string `json:"name"`
		} `json:"agency"`
	} `json:"route"`
}

type PlanResponse struct {
	Itineraries []Itinerary `json:"itineraries"`
}

type Itinerary struct {
	Duration int    `json:"duration"`
	Type     string `json:"type"` // "transit" or "walk"
	Legs     []ResponseLeg `json:"legs"`
}

type ResponseLeg struct {
	Mode        string  `json:"mode"`
	Duration    int     `json:"duration"`
	Distance    float64 `json:"distance"`
	VehicleType string  `json:"vehicleType,omitempty"`
	Agency      string  `json:"agency,omitempty"`
	From        string  `json:"from"`
	To          string  `json:"to"`
}

type PathRequest struct {
	From Coordinate `json:"from"`
	To   Coordinate `json:"to"`
}
type Coordinate struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

func getPath(w http.ResponseWriter, req *http.Request) {
	body, _ := io.ReadAll(req.Body)
	defer req.Body.Close()
	var PathRequestInput PathRequest
	err := json.Unmarshal(body, &PathRequestInput)
	if err != nil {
		log.Fatal(err)
	}

	query := fmt.Sprintf(`{"query":"{ plan(from:{lat:%f,lon:%f}, to:{lat:%f,lon:%f}, transportModes:[{mode:BUS},{mode:WALK}]) { itineraries { duration legs { mode duration distance from { name } to { name } route { shortName agency { name } } } } } }"}`,
		PathRequestInput.From.Lat, PathRequestInput.From.Lon,
		PathRequestInput.To.Lat, PathRequestInput.To.Lon,
	)
	url := "http://localhost:8080/otp/gtfs/v1"
	otpReq, err := http.NewRequest("POST", url, bytes.NewBuffer([]byte(query)))
	if err != nil {
		log.Printf("Error creating request: %v", err)
		return
	}
	otpReq.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(otpReq)
	if err != nil {
		log.Printf("Error calling OTP: %v", err)
		return
	}
	defer resp.Body.Close()

	body, err = io.ReadAll(resp.Body)
	if err != nil {
		log.Printf("Error reading OTP response: %v", err)
		return
	}

	var otpResp OTPResponse
	err = json.Unmarshal(body, &otpResp)
	if err != nil {
		log.Printf("Error parsing OTP response: %v", err)
		return
	}

	if len(otpResp.Data.Plan.Itineraries) == 0 {
		fmt.Fprint(w, "no itineraries found")
		return
	}

	// Build response with vehicle types
	var response PlanResponse
	for _, itin := range otpResp.Data.Plan.Itineraries {
		itiType := "transit"
		if len(itin.Legs) == 1 && itin.Legs[0].Mode == "WALK" {
			itiType = "walk"
		}

		var legs []ResponseLeg
		for _, leg := range itin.Legs {
			vehicleType := ""
			agency := ""
			if leg.Mode == "BUS" && leg.Route.ShortName != "" {
				vehicleType = leg.Route.ShortName
				agency = leg.Route.Agency.Name
			}
			legs = append(legs, ResponseLeg{
				Mode:        leg.Mode,
				Duration:    int(leg.Duration),
				Distance:    leg.Distance,
				VehicleType: vehicleType,
				Agency:      agency,
				From:        leg.From.Name,
				To:          leg.To.Name,
			})
		}

		response.Itineraries = append(response.Itineraries, Itinerary{
			Duration: itin.Duration,
			Type:     itiType,
			Legs:     legs,
		})
	}

	sort.Slice(response.Itineraries, func(i, j int) bool {
		return response.Itineraries[i].Duration < response.Itineraries[j].Duration
	})

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

func main() {
	http.HandleFunc("/hello", hello)
	http.HandleFunc("/getPath", getPath)
	log.Println("listening on :8090")
	http.ListenAndServe(":8090", nil)
}
