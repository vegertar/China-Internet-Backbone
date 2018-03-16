package main

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"

	prompt "github.com/c-bata/go-prompt"
	"github.com/mitchellh/mapstructure"
	"github.com/wangtuanjie/ip17mon"
	"github.com/yl2chen/cidranger"
)

type Area struct {
	ID         string `mapstructure:"id"`
	ParentID   string `mapstructure:"parent_id"`
	Level      string `mapstructure:"level"`
	AreaCode   string `mapstructure:"area_code"`
	ZipCode    string `mapstructure:"zip_code"`
	CityCode   string `mapstructure:"city_code"`
	Name       string `mapstructure:"name"`
	ShortName  string `mapstructure:"short_name"`
	MergerName string `mapstructure:"merger_name"`
	Pinyin     string `mapstructure:"pinyin"`
	Lng        string `mapstructure:"lng"`
	Lat        string `mapstructure:"lat"`
}

type Network struct {
	ASN    int
	ASName string
	CIDR   string
	ISP    string
}

func (n Network) Network() net.IPNet {
	_, network, err := net.ParseCIDR(n.CIDR)
	if err != nil {
		panic(err)
	}
	return *network
}

func (n Network) Record() []string {
	return []string{
		strconv.Itoa(n.ASN),
		n.ASName,
		n.CIDR,
		n.ISP,
	}
}

type RIB struct {
	ASN  int
	CIDR string
}

type Library struct {
	area map[string]Area
	net  cidranger.Ranger
}

func (l *Library) Find(ip string) (loc *ip17mon.LocationInfo, area Area, entries []cidranger.RangerEntry, err error) {
	loc, err = ip17mon.Find(ip)
	if err != nil {
		return
	}

	area, _ = l.getArea(loc.Country, loc.Region, loc.City)
	entries, err = l.net.ContainingNetworks(net.ParseIP(ip))

	return
}

func (l *Library) getArea(country, region, city string) (area Area, ok bool) {
	if country == "中国" {
		area, ok = l.area[region+","+city]
		if !ok {
			area, ok = l.area[region]
		}
	}
	return
}

func (l *Library) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	ip := req.URL.Path[1:]

	loc, area, entries, err := library.Find(ip)
	if err != nil {
		http.Error(w, err.Error(), 400)
		return
	}

	v := make(map[string]interface{})
	v["Country"] = loc.Country
	v["Region"] = loc.Region
	v["City"] = loc.City
	v["Lng"] = area.Lng
	v["Lat"] = area.Lat
	v["Networks"] = entries
	v["Source"] = "IPIP.net's free data plan"
	b, err := json.Marshal(v)
	if err != nil {
		http.Error(w, err.Error(), 400)
		return
	}
	w.Write(b)
}

var library *Library

func executor(in string) {
	loc, area, entries, err := library.Find(in)
	if err != nil {
		fmt.Println(err)
		return
	}

	b, err := json.MarshalIndent(loc, "", "  ")
	if err != nil {
		fmt.Println(err)
		return
	}

	fmt.Println(string(b))

	b, err = json.MarshalIndent(area, "", "  ")
	if err != nil {
		fmt.Println(err)
		return
	}

	fmt.Println(string(b))

	for _, entry := range entries {
		network := entry.(Network)
		b, err = json.MarshalIndent(network, "", "  ")
		if err != nil {
			fmt.Println(err)
			return
		}
		fmt.Println(string(b))
	}
}

func completer(t prompt.Document) []prompt.Suggest {
	return []prompt.Suggest{}
}

func columnTrim(s string) string {
	return strings.Trim(strings.TrimSpace(s), "'\"`")
}

func scanColumns(s string) (columns []string) {
	columns = make([]string, 0, 12)
	s = strings.TrimSpace(s)
	start := 0

	var quote byte
	for i := 0; i < len(s); i++ {
		switch s[i] {
		case '"', '\'', '`':
			if quote == 0 {
				quote = s[i]
			} else if quote == s[i] {
				quote = 0
			}
		case ',':
			if quote == 0 {
				columns = append(columns, columnTrim(s[start:i]))
				start = i + 1
			}
		}
	}

	if start < len(s) {
		columns = append(columns, columnTrim(s[start:]))
	}
	return
}

func scanTitles(s string) []string {
	block, _ := scanBlock(s)
	return scanColumns(block)
}

func scanValues(s string) <-chan []string {
	ch := make(chan []string)
	go func() {
		defer close(ch)

		var block string
		for s != "" {
			block, s = scanBlock(s)
			if block != "" {
				ch <- scanColumns(block)
			}
		}
	}()
	return ch
}

func scanBlock(s string) (block string, rest string) {
	start := strings.IndexByte(s, '(')
	if start != -1 {
		brackets := 0
		var quote byte
		for i := start + 1; i < len(s); i++ {
			switch s[i] {
			case '"', '\'', '`':
				if quote == 0 {
					quote = s[i]
				} else if quote == s[i] {
					quote = 0
				}
			case '(':
				if quote == 0 {
					brackets++
				}
			case ')':
				if quote == 0 {
					if brackets == 0 {
						return s[start+1 : i], s[i+1:]
					}
					brackets--
				}
			}
		}
	}
	return "", ""
}

func parseAsNames() map[int]string {
	const asNamesPath = "asn/asnames.txt"
	log.Println("Trying to load AS names from", asNamesPath)

	asFile, err := os.Open(asNamesPath)
	if err != nil {
		panic(err)
	}

	reader := bufio.NewReader(asFile)
	m := make(map[int]string)

	for {
		line, err := reader.ReadString('\n')
		line = strings.TrimSpace(line)
		if strings.HasSuffix(line, ", CN") {
			space := strings.IndexByte(line, ' ')
			number, err := strconv.Atoi(line[:space][2:])
			if err != nil {
				panic(err)
			}
			i := space + 1
			for ; i < len(line) && line[i] == ' '; i++ {
				// nop
			}
			if i == len(line) {
				panic("invalid line:" + line)
			}
			name := line[i:]
			m[number] = name
		}
		if err != nil {
			break
		}
	}

	return m
}

func parseRIB() <-chan RIB {
	const ribPath = "asn/rib.txt"
	log.Println("Trying to load RIB data from", ribPath)

	ribFile, err := os.Open(ribPath)
	if err != nil {
		panic(err)
	}

	reader := bufio.NewReader(ribFile)
	ch := make(chan RIB)
	go func() {
		defer close(ch)

		for {
			line, err := reader.ReadString('\n')
			line = strings.TrimSpace(line)
			if line != "" {
				items := strings.Split(line, "|")
				cidr, asPath, aggregator := items[5], items[6], items[13]
				if cidr != "0.0.0.0/0" && cidr != "::/0" {
					var aggregatorAs int
					if t := strings.Split(aggregator, " "); len(t) > 0 {
						aggregatorAs, _ = strconv.Atoi(t[0])
					}

					asList := make([]int, 0, 4)
					for _, s := range strings.Split(strings.TrimSpace(asPath), " ") {
						n, err := strconv.Atoi(s)
						if err != nil {
							n = aggregatorAs
						}
						asList = append(asList, n)
					}

					if len(asList) > 0 {
						ch <- RIB{
							ASN:  asList[len(asList)-1],
							CIDR: cidr,
						}
					} else {
						log.Println("Not found valid AS within", items)
					}
				}
			}

			if err != nil {
				break
			}
		}
	}()

	return ch
}

func parseNetwork() <-chan Network {
	ch := make(chan Network)

	go func() {
		defer close(ch)

		const networkPath = "network.csv"
		log.Println("Loading cached network from", networkPath)

		networkFile, err := os.Open(networkPath)
		if err != nil {
			log.Println(err)

			type ISP struct {
				Name    string
				Pattern *regexp.Regexp
			}

			isps := []ISP{
				{
					Name:    "联通",
					Pattern: regexp.MustCompile("(?i)(unicom|cnc)"),
				},
				{
					Name:    "铁通",
					Pattern: regexp.MustCompile("(?i)tietong"),
				},
				{
					Name:    "电信",
					Pattern: regexp.MustCompile("(?i)(china ?telecom|chinanet)"),
				},
				{
					Name:    "移动",
					Pattern: regexp.MustCompile("(?i)mobile"),
				},
				{
					Name:    "教育网",
					Pattern: regexp.MustCompile("(?i)cernet"),
				},
				{
					Name:    "科技网",
					Pattern: regexp.MustCompile("(?i)cstnet"),
				},
				{
					Name:    "鹏博士",
					Pattern: regexp.MustCompile("(?i)(dxtnet|dr.?peng)"),
				},
			}

			asIsps := make(map[int]string)
			asNames := parseAsNames()
			for asn, name := range asNames {
				for _, isp := range isps {
					if isp.Pattern.MatchString(name) {
						asIsps[asn] = isp.Name
					}
				}
			}

			networkFile, err = os.OpenFile(networkPath+".tmp", os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
			if err != nil {
				panic(err)
			}

			w := csv.NewWriter(networkFile)
			uniq := make(map[string]bool)

			for rib := range parseRIB() {
				name, ok := asNames[rib.ASN]
				if ok {
					network := Network{
						ASN:    rib.ASN,
						ASName: name,
						CIDR:   rib.CIDR,
						ISP:    asIsps[rib.ASN],
					}
					record := network.Record()
					k := strings.Join(record, "|")
					if uniq[k] {
						continue
					}

					uniq[k] = true
					ch <- network

					if err := w.Write(record); err != nil {
						panic(err)
					}
				}
			}

			w.Flush()
			if err := w.Error(); err != nil {
				panic(err)
			}

			os.Rename(networkPath+".tmp", networkPath)
			log.Println("Saved network data")
		} else {
			r := csv.NewReader(networkFile)

			for {
				record, err := r.Read()
				if err == io.EOF {
					break
				}

				if err != nil {
					panic(err)
				}

				var network Network

				network.ASN, err = strconv.Atoi(record[0])
				if err != nil {
					panic(err)
				}

				network.ASName = record[1]
				network.CIDR = record[2]
				network.ISP = record[3]

				ch <- network
			}
		}
	}()

	return ch
}

func loadNetwork() cidranger.Ranger {
	ranger := cidranger.NewPCTrieRanger()
	for network := range parseNetwork() {
		ranger.Insert(network)
	}
	return ranger
}

func parseArea() map[string]Area {
	const areaPath = "china_area_mysql/cnarea20160731.sql"
	log.Println("Trying to parse area from", areaPath)

	areaFile, err := os.Open(areaPath)
	if err != nil {
		panic(err)
	}

	b, err := ioutil.ReadAll(areaFile)
	if err != nil {
		panic(err)
	}

	sql := string(b)
	insertStatement := sql[strings.Index(sql, "insert"):]
	valuesIndex := strings.Index(insertStatement, "values")
	titles := scanTitles(insertStatement[:valuesIndex])

	m := make(map[string]Area)
	for values := range scanValues(insertStatement[valuesIndex:]) {
		var area Area

		t := make(map[string]string)
		for i := 0; i < len(titles); i++ {
			t[titles[i]] = values[i]
		}

		err := mapstructure.Decode(t, &area)
		if err != nil {
			panic(err)
		}

		// encounters a title
		if area.MergerName == "merger_name" {
			continue
		}

		if strings.Count(area.MergerName, ",") <= 1 {
			m[area.MergerName] = area
		}
	}

	return m
}

func loadArea() (m map[string]Area) {
	const areaPath = "area.json"
	log.Println("Loading cached area from", areaPath)

	areaFile, err := os.Open(areaPath)
	if err != nil {
		log.Println(err)

		m = parseArea()

		areaFile, err = os.OpenFile(areaPath+".tmp", os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
		if err != nil {
			panic(err)
		}

		b, err := json.Marshal(m)
		if err != nil {
			panic(err)
		}

		if _, err := areaFile.Write(b); err != nil {
			log.Println(err)
		} else {
			os.Rename(areaPath+".tmp", areaPath)
			log.Println("Saved area cache")
		}
	} else {
		b, err := ioutil.ReadAll(areaFile)
		if err != nil {
			panic(err)
		}
		if err := json.Unmarshal(b, &m); err != nil {
			panic(err)
		}
	}

	log.Println("Contained", len(m), "areas")
	return
}

func main() {
	interpret := flag.Bool("i", false, "run as an interpeter")
	addr := flag.String("addr", "", "run on the given address")

	flag.Parse()

	if err := ip17mon.Init("ipip/17monipdb.dat"); err != nil {
		panic(err)
	}

	library = &Library{
		area: loadArea(),
		net:  loadNetwork(),
	}

	if *addr != "" {
		log.Println("Listening on", *addr)
		http.ListenAndServe(*addr, library)
	}

	if *interpret {
		prompt.New(executor, completer).Run()
	}
}
