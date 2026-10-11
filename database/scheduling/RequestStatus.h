#ifndef REQUEST_STATUS_H
#define REQUEST_STATUS_H

#include <map>
#include <string>

enum class RequestState
{
    Pending,
    Processing,
    Completed,
    Cancelled
};

class RequestStatusManager
{
private:
    std::map<int, RequestState> statusMap;

public:
    void registerRequest(int requestId);

    bool updateStatus(int requestId, RequestState newStatus);

    RequestState getStatus(int requestId) const;

    void displayStatus(int requestId) const;

    static std::string getStatusName(RequestState status);
};

#endif