import requests, json
class MicroserviceBase:
    """
    Base class for microservices in the Pitxu system. This class provides common functionality to Server and Client.
    """

    PROTOCOL: str = "http"

    def _do_get_request(self, endpoint: str):
        url = self._build_url(endpoint=endpoint)
        response = requests.get(url)
        return json.loads(response.content)
    
    def _do_post_request(self, endpoint: str, data: dict):
        url = self._build_url(endpoint=endpoint)
        response = requests.post(url, json=data)
        if response is not None:
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                return {
                    "request": response.request,
                    "status_code": response.status_code,
                    "reason": response.reason,
                }
        else:
            return None
    
    def _build_url(self, endpoint: str):
        url = self.PROTOCOL + "://" + \
            self._xconfig.get("client.host") + \
            ":" + str(self._xconfig.get("client.port")) + \
            "/" + endpoint
        return url
    